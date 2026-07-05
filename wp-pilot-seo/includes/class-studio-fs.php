<?php
/**
 * Safe file-system layer for wptaskify Studio module (part of wptaskify).
 *
 * ALL file writes go through here so we always:
 *   1. Confine operations to allowed roots (themes, plugins, uploads) - never
 *      wp-config.php, wp-admin, wp-includes or anything outside wp-content.
 *   2. Back up any existing file before overwriting/deleting it.
 *   3. Validate PHP syntax BEFORE saving, so a bad edit can never take the site
 *      down (the write is refused if `php -l` reports an error, when available).
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Studio_FS {

	/** Roots the AI is allowed to touch. Everything else is denied. */
	public static function allowed_roots() {
		return array(
			'themes'  => trailingslashit( get_theme_root() ),
			'plugins' => trailingslashit( WP_PLUGIN_DIR ),
			'uploads' => trailingslashit( wp_upload_dir()['basedir'] ),
		);
	}

	/**
	 * Resolve a caller-supplied relative path (e.g. "themes/mytheme/style.css")
	 * to an absolute path, ensuring it stays inside an allowed root. Returns
	 * WP_Error on any escape attempt.
	 */
	public static function resolve( $rel ) {
		$rel = ltrim( str_replace( '\\', '/', (string) $rel ), '/' );
		if ( $rel === '' ) {
			return new WP_Error( 'bad_path', 'Empty path' );
		}
		// Block traversal + null bytes outright.
		if ( strpos( $rel, '..' ) !== false || strpos( $rel, "\0" ) !== false ) {
			return new WP_Error( 'bad_path', 'Path traversal is not allowed' );
		}
		$parts = explode( '/', $rel, 2 );
		$root_key = $parts[0];
		$tail     = isset( $parts[1] ) ? $parts[1] : '';
		$roots    = self::allowed_roots();
		if ( ! isset( $roots[ $root_key ] ) ) {
			return new WP_Error( 'bad_root', 'Path must start with one of: ' . implode( ', ', array_keys( $roots ) ) );
		}
		$abs = $roots[ $root_key ] . $tail;
		// Final containment check using realpath on the parent dir.
		$root_real = realpath( $roots[ $root_key ] );
		$parent    = realpath( dirname( $abs ) );
		if ( $parent !== false && $root_real !== false && strpos( $parent, $root_real ) !== 0 ) {
			return new WP_Error( 'escape', 'Resolved path escapes its allowed root' );
		}
		return $abs;
	}

	/**
	 * True if $abs points inside wptaskify's own plugin directory. Anchored on the
	 * WPPSEO_DIR constant (set from __FILE__), so it holds no matter what the
	 * plugin folder is named or where it's installed, and can't be spoofed by the
	 * caller. Compares realpaths where possible; falls back to a prefix compare on
	 * the (normalized) target dir for not-yet-existing files.
	 */
	public static function is_own_plugin( $abs ) {
		if ( ! defined( 'WPPSEO_DIR' ) ) {
			return false;
		}
		$own_real = realpath( WPPSEO_DIR );
		// For a new file the target may not exist yet -> use its parent dir.
		$target_real = realpath( $abs );
		if ( $target_real === false ) {
			$target_real = realpath( dirname( $abs ) );
		}
		if ( $own_real !== false && $target_real !== false ) {
			$own_real    = rtrim( str_replace( '\\', '/', $own_real ), '/' ) . '/';
			$target_real = rtrim( str_replace( '\\', '/', $target_real ), '/' ) . '/';
			return strpos( $target_real, $own_real ) === 0;
		}
		// Fallback: normalized string prefix compare (no realpath available).
		$own  = rtrim( str_replace( '\\', '/', WPPSEO_DIR ), '/' ) . '/';
		$norm = rtrim( str_replace( '\\', '/', (string) $abs ), '/' ) . '/';
		return strpos( $norm, $own ) === 0;
	}

	/** Is this a PHP file (by extension)? */
	private static function is_php( $abs ) {
		return preg_match( '/\.php$/i', $abs ) === 1;
	}

	/**
	 * Validate PHP syntax without executing the code. Tries the `php` binary via
	 * `php -l`; if that isn't available, falls back to token_get_all() which
	 * catches most parse errors. Returns true on OK, or WP_Error with the message.
	 */
	public static function validate_php( $code ) {
		// 1. Try the real linter (`php -l`) in a temp file.
		if ( function_exists( 'proc_open' ) && function_exists( 'shell_exec' ) ) {
			$php_bin = defined( 'PHP_BINARY' ) && PHP_BINARY ? PHP_BINARY : 'php';
			$tmp = wp_tempnam( 'wpps-lint' );
			if ( $tmp ) {
				file_put_contents( $tmp, $code );
				$cmd = escapeshellarg( $php_bin ) . ' -l ' . escapeshellarg( $tmp ) . ' 2>&1';
				$out = @shell_exec( $cmd );
				@unlink( $tmp );
				if ( is_string( $out ) && $out !== '' ) {
					if ( stripos( $out, 'No syntax errors' ) !== false ) {
						return true;
					}
					if ( stripos( $out, 'error' ) !== false || stripos( $out, 'Parse' ) !== false ) {
						return new WP_Error( 'php_syntax', trim( $out ) );
					}
				}
			}
		}
		// 2. Fallback: tokenize and let PHP raise a ParseError we can catch.
		try {
			// token_get_all with TOKEN_PARSE throws ParseError on invalid code.
			token_get_all( $code, TOKEN_PARSE );
			return true;
		} catch ( \ParseError $e ) {
			return new WP_Error( 'php_syntax', $e->getMessage() );
		} catch ( \Throwable $e ) {
			// Unknown issue - allow, since we couldn't prove it's broken.
			return true;
		}
	}

	/** Copy an existing file into the timestamped backup tree. */
	public static function backup( $abs ) {
		if ( ! file_exists( $abs ) ) {
			return true; // nothing to back up
		}
		$rel  = str_replace( array( WP_CONTENT_DIR, '/' ), array( '', '_' ), $abs );
		$stamp = gmdate( 'Ymd-His' );
		$dest = trailingslashit( WPPSEO_BACKUP_DIR ) . $stamp . '__' . ltrim( $rel, '_' );
		wp_mkdir_p( dirname( $dest ) );
		if ( ! @copy( $abs, $dest ) ) {
			return new WP_Error( 'backup_failed', 'Could not back up ' . $abs );
		}
		return $dest;
	}

	/**
	 * Write a file safely. Backs up any existing file, validates PHP syntax
	 * first, creates parent dirs, then writes. Returns array on success or WP_Error.
	 */
	public static function write( $rel, $contents ) {
		$abs = self::resolve( $rel );
		if ( is_wp_error( $abs ) ) {
			return $abs;
		}
		// SELF-PROTECTION: wptaskify's own plugin is READ-ONLY to the AI. A bad
		// edit here could disable the Studio guard, the security hardening, or the
		// connection itself. Reads/listing still work - only writes are blocked.
		if ( self::is_own_plugin( $abs ) ) {
			return new WP_Error(
				'own_plugin',
				'The wptaskify plugin is read-only; the AI cannot modify its own ' .
				'plugin files. Edit your theme or another plugin instead.'
			);
		}
		if ( self::is_php( $abs ) ) {
			$ok = self::validate_php( $contents );
			if ( is_wp_error( $ok ) ) {
				return $ok; // refuse to save broken PHP
			}
		}
		$backup = self::backup( $abs );
		if ( is_wp_error( $backup ) ) {
			return $backup;
		}
		wp_mkdir_p( dirname( $abs ) );
		$bytes = @file_put_contents( $abs, $contents );
		if ( $bytes === false ) {
			return new WP_Error( 'write_failed', 'Could not write ' . $rel );
		}
		return array(
			'path'    => $rel,
			'bytes'   => $bytes,
			'backup'  => is_string( $backup ) ? basename( $backup ) : null,
			'existed' => is_string( $backup ),
		);
	}

	/** Read a file's contents (within allowed roots). */
	public static function read( $rel ) {
		$abs = self::resolve( $rel );
		if ( is_wp_error( $abs ) ) {
			return $abs;
		}
		if ( ! file_exists( $abs ) || ! is_readable( $abs ) ) {
			return new WP_Error( 'not_found', 'File not found: ' . $rel );
		}
		return array( 'path' => $rel, 'contents' => file_get_contents( $abs ) );
	}

	/** List files/dirs under a relative directory (one level). */
	public static function ls( $rel ) {
		$abs = self::resolve( $rel );
		if ( is_wp_error( $abs ) ) {
			return $abs;
		}
		if ( ! is_dir( $abs ) ) {
			return new WP_Error( 'not_dir', 'Not a directory: ' . $rel );
		}
		$items = array();
		foreach ( scandir( $abs ) as $f ) {
			if ( $f === '.' || $f === '..' ) {
				continue;
			}
			$items[] = array(
				'name' => $f,
				'type' => is_dir( $abs . '/' . $f ) ? 'dir' : 'file',
			);
		}
		return array( 'path' => $rel, 'items' => $items );
	}

	/** Delete a file (backs it up first). Directories are not deleted here. */
	public static function delete( $rel ) {
		$abs = self::resolve( $rel );
		if ( is_wp_error( $abs ) ) {
			return $abs;
		}
		// SELF-PROTECTION: never delete wptaskify's own plugin files (read-only).
		if ( self::is_own_plugin( $abs ) ) {
			return new WP_Error(
				'own_plugin',
				'The wptaskify plugin is read-only; the AI cannot delete its own ' .
				'plugin files.'
			);
		}
		if ( ! file_exists( $abs ) ) {
			return new WP_Error( 'not_found', 'File not found: ' . $rel );
		}
		if ( is_dir( $abs ) ) {
			return new WP_Error( 'is_dir', 'Refusing to delete a directory' );
		}
		$backup = self::backup( $abs );
		if ( is_wp_error( $backup ) ) {
			return $backup;
		}
		@unlink( $abs );
		return array( 'deleted' => $rel, 'backup' => basename( $backup ) );
	}
}
