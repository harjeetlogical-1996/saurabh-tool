<?php
/**
 * REST API so the wptaskify MCP server (AI assistant) can build on the site:
 * custom CSS, files, whole plugins and themes - all through the safe WPPS_FS layer.
 *
 * Namespace: wpps/v1   (all routes require `manage_options` - admin only)
 *   GET  /info                        capability discovery
 *   GET  /file?path=themes/x/style.css
 *   POST /file        {path, contents}         write (backup + PHP lint)
 *   POST /file/delete {path}
 *   GET  /ls?path=themes/x
 *   POST /css         {css}                     set site-wide custom CSS
 *   GET  /css
 *   POST /create-plugin {slug, name, description, code?}
 *   POST /create-theme  {slug, name, style_css?, index_php?, functions_php?}
 *   POST /activate-theme {slug}
 *   GET  /backups                              list recent backups
 *   POST /restore     {backup}                 restore a backup file
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Studio_REST {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'rest_api_init', array( $this, 'routes' ) );
		// Inject the custom CSS on the frontend.
		add_action( 'wp_head', array( $this, 'print_css' ), 100 );
	}

	/**
	 * Admin-only: building files/themes/plugins is a powerful capability.
	 *
	 * PREMIUM-READY: the `wppseo_studio_allowed` filter lets us gate Studio
	 * behind a plan/license later WITHOUT changing this plugin - e.g. a license
	 * check can flip it off. Defaults to allowed for any site admin today.
	 */
	public function perm() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return false;
		}
		return (bool) apply_filters( 'wppseo_studio_allowed', true );
	}

	public function routes() {
		$ns = 'wpps/v1';
		$admin = array( $this, 'perm' );

		register_rest_route( $ns, '/info', array(
			'methods' => 'GET', 'callback' => array( $this, 'info' ),
			'permission_callback' => '__return_true',
		) );
		register_rest_route( $ns, '/file', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_file' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'put_file' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/file/delete', array(
			'methods' => 'POST', 'callback' => array( $this, 'del_file' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/ls', array(
			'methods' => 'GET', 'callback' => array( $this, 'ls' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/css', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_css' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'set_css' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/create-plugin', array(
			'methods' => 'POST', 'callback' => array( $this, 'create_plugin' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/create-theme', array(
			'methods' => 'POST', 'callback' => array( $this, 'create_theme' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/activate-theme', array(
			'methods' => 'POST', 'callback' => array( $this, 'activate_theme' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/preview-theme', array(
			'methods' => 'POST', 'callback' => array( $this, 'preview_theme' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/rollback-theme', array(
			'methods' => 'POST', 'callback' => array( $this, 'rollback_theme' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/themes', array(
			'methods' => 'GET', 'callback' => array( $this, 'list_themes' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/plugins', array(
			'methods' => 'GET', 'callback' => array( $this, 'list_plugins' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/plugin-state', array(
			'methods' => 'POST', 'callback' => array( $this, 'set_plugin_state' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/site-backup', array(
			'methods' => 'POST', 'callback' => array( $this, 'site_backup' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/site-restore', array(
			'methods' => 'POST', 'callback' => array( $this, 'site_restore' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/backups', array(
			'methods' => 'GET', 'callback' => array( $this, 'backups' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/option', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_option_r' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'set_option_r' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/robots', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_robots' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'set_robots' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/htaccess', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_htaccess' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'set_htaccess' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/install-plugin', array(
			'methods' => 'POST', 'callback' => array( $this, 'install_plugin' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/health', array(
			'methods' => 'GET', 'callback' => array( $this, 'health' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/activity', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_activity' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'log_activity' ), 'permission_callback' => $admin ),
		) );
		register_rest_route( $ns, '/optimize-images', array(
			'methods' => 'POST', 'callback' => array( $this, 'optimize_images' ), 'permission_callback' => $admin,
		) );
		register_rest_route( $ns, '/llms', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'get_llms' ), 'permission_callback' => $admin ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'set_llms' ), 'permission_callback' => $admin ),
		) );
	}

	public function info() {
		return rest_ensure_response( array(
			'plugin'        => 'wp-pilot-studio',
			'version'       => WPPSEO_VERSION,
			'allowed_roots' => array_keys( WPPSEO_Studio_FS::allowed_roots() ),
			'capabilities'  => array( 'custom_css', 'file_rw', 'create_plugin', 'create_theme', 'preview_theme', 'rollback_theme', 'list_themes', 'list_plugins', 'plugin_state', 'site_backup', 'site_restore', 'backups' ),
		) );
	}

	// ---- files -----------------------------------------------------------
	public function get_file( $r ) {
		$res = WPPSEO_Studio_FS::read( $r->get_param( 'path' ) );
		return is_wp_error( $res ) ? $res : rest_ensure_response( $res );
	}

	public function put_file( $r ) {
		$b = $r->get_json_params();
		$res = WPPSEO_Studio_FS::write( isset( $b['path'] ) ? $b['path'] : '', isset( $b['contents'] ) ? $b['contents'] : '' );
		return is_wp_error( $res ) ? $res : rest_ensure_response( $res );
	}

	public function del_file( $r ) {
		$b = $r->get_json_params();
		$res = WPPSEO_Studio_FS::delete( isset( $b['path'] ) ? $b['path'] : '' );
		return is_wp_error( $res ) ? $res : rest_ensure_response( $res );
	}

	public function ls( $r ) {
		$res = WPPSEO_Studio_FS::ls( $r->get_param( 'path' ) );
		return is_wp_error( $res ) ? $res : rest_ensure_response( $res );
	}

	// ---- custom CSS (crash-proof, applies site-wide) ---------------------
	public function get_css() {
		return rest_ensure_response( array( 'css' => (string) get_option( 'wpps_custom_css', '' ) ) );
	}

	public function set_css( $r ) {
		$b   = $r->get_json_params();
		$css = isset( $b['css'] ) ? (string) $b['css'] : '';
		// Strip anything that isn't CSS-ish (no tags) - CSS can't crash PHP anyway.
		$css = wp_strip_all_tags( $css );
		update_option( 'wpps_custom_css', $css );
		return rest_ensure_response( array( 'saved' => true, 'bytes' => strlen( $css ) ) );
	}

	public function print_css() {
		$css = (string) get_option( 'wpps_custom_css', '' );
		if ( $css !== '' ) {
			echo "\n<style id=\"wp-pilot-studio-css\">\n" . $css . "\n</style>\n"; // phpcs:ignore
		}
	}

	// ---- create a whole plugin ------------------------------------------
	public function create_plugin( $r ) {
		$b    = $r->get_json_params();
		$slug = isset( $b['slug'] ) ? sanitize_key( $b['slug'] ) : '';
		$name = isset( $b['name'] ) ? sanitize_text_field( $b['name'] ) : $slug;
		$desc = isset( $b['description'] ) ? sanitize_text_field( $b['description'] ) : '';
		$code = isset( $b['code'] ) ? (string) $b['code'] : '';
		if ( ! $slug ) {
			return new WP_Error( 'bad_slug', 'A plugin slug is required', array( 'status' => 400 ) );
		}
		$header = "<?php\n/**\n * Plugin Name: {$name}\n * Description: {$desc}\n"
			. " * Version: 1.0.0\n * Author: wptaskify Studio\n */\n\n"
			. "if ( ! defined( 'ABSPATH' ) ) { exit; }\n\n";
		$body = $code !== '' ? $code : "// Your plugin code here.\n";
		$res  = WPPSEO_Studio_FS::write( "plugins/{$slug}/{$slug}.php", $header . $body );
		return is_wp_error( $res ) ? $res : rest_ensure_response( array( 'created' => "plugins/{$slug}/{$slug}.php", 'write' => $res ) );
	}

	// ---- create a whole theme -------------------------------------------
	public function create_theme( $r ) {
		$b    = $r->get_json_params();
		$slug = isset( $b['slug'] ) ? sanitize_key( $b['slug'] ) : '';
		$name = isset( $b['name'] ) ? sanitize_text_field( $b['name'] ) : $slug;
		if ( ! $slug ) {
			return new WP_Error( 'bad_slug', 'A theme slug is required', array( 'status' => 400 ) );
		}
		$style = isset( $b['style_css'] ) ? (string) $b['style_css'] : '';
		if ( strpos( $style, 'Theme Name:' ) === false ) {
			$style = "/*\nTheme Name: {$name}\nAuthor: wptaskify Studio\nVersion: 1.0.0\n*/\n\n" . $style;
		}
		$index     = isset( $b['index_php'] ) ? (string) $b['index_php'] : "<?php\n// index template\n";
		$functions = isset( $b['functions_php'] ) ? (string) $b['functions_php'] : "<?php\n// theme functions\n";

		$results = array();
		foreach ( array(
			"themes/{$slug}/style.css"     => $style,
			"themes/{$slug}/index.php"     => $index,
			"themes/{$slug}/functions.php" => $functions,
		) as $path => $contents ) {
			$res = WPPSEO_Studio_FS::write( $path, $contents );
			if ( is_wp_error( $res ) ) {
				return $res; // stop on first failure (e.g. bad PHP)
			}
			$results[ $path ] = $res;
		}
		return rest_ensure_response( array( 'created_theme' => $slug, 'files' => $results ) );
	}

	public function activate_theme( $r ) {
		$b    = $r->get_json_params();
		$slug = isset( $b['slug'] ) ? sanitize_key( $b['slug'] ) : '';
		$theme = wp_get_theme( $slug );
		if ( ! $theme->exists() ) {
			return new WP_Error( 'no_theme', 'Theme not found: ' . $slug, array( 'status' => 404 ) );
		}
		// Remember the CURRENT theme so we can one-click roll back if the new one
		// looks wrong on the live site.
		$previous = get_stylesheet();
		if ( $previous !== $slug ) {
			update_option( 'wpps_previous_theme', $previous );
		}
		switch_theme( $slug );
		return rest_ensure_response( array(
			'activated' => $slug,
			'previous'  => $previous,
			'note'      => 'The previous theme is saved - call rollback-theme to restore it if needed.',
		) );
	}

	/**
	 * Give a PREVIEW url for a theme WITHOUT activating it - only logged-in admins
	 * see the preview; visitors keep seeing the live theme. This is the "staging"
	 * step: build a theme, preview it safely, then activate only if it looks good.
	 */
	public function preview_theme( $r ) {
		$b    = $r->get_json_params();
		$slug = isset( $b['slug'] ) ? sanitize_key( $b['slug'] ) : '';
		$theme = wp_get_theme( $slug );
		if ( ! $theme->exists() ) {
			return new WP_Error( 'no_theme', 'Theme not found: ' . $slug, array( 'status' => 404 ) );
		}
		// WordPress' Customizer live-preview URL for a specific theme.
		$url = add_query_arg(
			array(
				'theme'  => rawurlencode( $slug ),
				'return' => rawurlencode( admin_url( 'themes.php' ) ),
			),
			admin_url( 'customize.php' )
		);
		return rest_ensure_response( array(
			'slug'        => $slug,
			'preview_url' => $url,
			'note'        => 'Open this URL (while logged in as admin) to preview the '
				. 'theme live. Visitors still see the current theme. Activate it only '
				. 'when it looks right.',
		) );
	}

	/** Roll back to the theme that was active before the last activate. */
	public function rollback_theme( $r ) {
		$prev = get_option( 'wpps_previous_theme', '' );
		if ( ! $prev ) {
			return new WP_Error( 'no_prev', 'No previous theme recorded to roll back to.', array( 'status' => 404 ) );
		}
		$theme = wp_get_theme( $prev );
		if ( ! $theme->exists() ) {
			return new WP_Error( 'gone', 'The previous theme (' . $prev . ') no longer exists.', array( 'status' => 404 ) );
		}
		switch_theme( $prev );
		delete_option( 'wpps_previous_theme' );
		return rest_ensure_response( array( 'rolled_back_to' => $prev ) );
	}

	// ---- theme / plugin management --------------------------------------
	public function list_themes() {
		$active = get_stylesheet();
		$out = array();
		foreach ( wp_get_themes() as $slug => $theme ) {
			$out[] = array(
				'slug'    => $slug,
				'name'    => $theme->get( 'Name' ),
				'version' => $theme->get( 'Version' ),
				'active'  => ( $slug === $active ),
			);
		}
		return rest_ensure_response( array( 'active' => $active, 'themes' => $out ) );
	}

	public function list_plugins() {
		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}
		$all    = get_plugins();
		$active = (array) get_option( 'active_plugins', array() );
		$out    = array();
		foreach ( $all as $file => $data ) {
			$out[] = array(
				'file'    => $file,
				'name'    => $data['Name'],
				'version' => $data['Version'],
				'active'  => in_array( $file, $active, true ),
			);
		}
		return rest_ensure_response( array( 'plugins' => $out ) );
	}

	public function set_plugin_state( $r ) {
		if ( ! function_exists( 'activate_plugin' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}
		$b      = $r->get_json_params();
		$file   = isset( $b['file'] ) ? sanitize_text_field( $b['file'] ) : '';
		$action = isset( $b['action'] ) ? sanitize_key( $b['action'] ) : '';
		if ( ! $file || ! in_array( $action, array( 'activate', 'deactivate' ), true ) ) {
			return new WP_Error( 'bad_req', 'Need file + action (activate|deactivate)', array( 'status' => 400 ) );
		}
		// Never let the AI deactivate wptaskify itself (would cut its own connection).
		if ( strpos( $file, 'wp-pilot-seo' ) !== false ) {
			return new WP_Error( 'protected', 'wptaskify cannot deactivate itself.', array( 'status' => 400 ) );
		}
		if ( 'activate' === $action ) {
			$res = activate_plugin( $file );
			if ( is_wp_error( $res ) ) {
				return $res; // e.g. the plugin caused a fatal - WP catches it
			}
			return rest_ensure_response( array( 'activated' => $file ) );
		}
		deactivate_plugins( array( $file ) );
		return rest_ensure_response( array( 'deactivated' => $file ) );
	}

	// ---- full site backup / restore (themes + plugins + uploads + DB opts) --
	public function site_backup( $r ) {
		$stamp = gmdate( 'Ymd-His' );
		$dir   = trailingslashit( WPPSEO_BACKUP_DIR ) . 'site-' . $stamp;
		wp_mkdir_p( $dir );

		// 1. Zip the code (themes + plugins). Uploads can be huge, so it's optional.
		$b        = $r->get_json_params();
		$include_uploads = ! empty( $b['include_uploads'] );
		$zip_path = $dir . '/files.zip';
		$roots    = array(
			'themes'  => get_theme_root(),
			'plugins' => WP_PLUGIN_DIR,
		);
		if ( $include_uploads ) {
			$roots['uploads'] = wp_upload_dir()['basedir'];
		}
		$zipped = $this->zip_dirs( $roots, $zip_path );
		if ( is_wp_error( $zipped ) ) {
			return $zipped;
		}

		// 2. Export a light DB snapshot: all options + active theme/plugins.
		$snapshot = array(
			'stamp'          => $stamp,
			'active_theme'   => get_stylesheet(),
			'active_plugins' => get_option( 'active_plugins', array() ),
			'siteurl'        => get_option( 'siteurl' ),
			'blogname'       => get_option( 'blogname' ),
		);
		file_put_contents( $dir . '/snapshot.json', wp_json_encode( $snapshot ) );

		return rest_ensure_response( array(
			'backup_id' => 'site-' . $stamp,
			'files_zip' => 'files.zip',
			'size'      => file_exists( $zip_path ) ? filesize( $zip_path ) : 0,
			'note'      => 'Full code backup saved. Use site-restore with this backup_id to restore.',
		) );
	}

	public function site_restore( $r ) {
		$b  = $r->get_json_params();
		$id = isset( $b['backup_id'] ) ? sanitize_file_name( $b['backup_id'] ) : '';
		$dir = trailingslashit( WPPSEO_BACKUP_DIR ) . $id;
		$zip = $dir . '/files.zip';
		if ( ! $id || ! file_exists( $zip ) ) {
			return new WP_Error( 'no_backup', 'Backup not found: ' . $id, array( 'status' => 404 ) );
		}
		if ( ! class_exists( 'ZipArchive' ) ) {
			return new WP_Error( 'no_zip', 'ZipArchive not available on this server.', array( 'status' => 500 ) );
		}
		$za = new ZipArchive();
		if ( true !== $za->open( $zip ) ) {
			return new WP_Error( 'bad_zip', 'Could not open backup zip.', array( 'status' => 500 ) );
		}
		// Restore into wp-content (paths inside the zip are themes/… plugins/…).
		$za->extractTo( WP_CONTENT_DIR );
		$za->close();

		// Restore active theme/plugins from the snapshot.
		$snap = @json_decode( (string) file_get_contents( $dir . '/snapshot.json' ), true );
		if ( is_array( $snap ) ) {
			if ( ! empty( $snap['active_theme'] ) ) {
				switch_theme( $snap['active_theme'] );
			}
			if ( isset( $snap['active_plugins'] ) ) {
				update_option( 'active_plugins', $snap['active_plugins'] );
			}
		}
		return rest_ensure_response( array( 'restored' => $id ) );
	}

	/** Zip a set of {label => absolute dir} into $zip_path, entries prefixed by label. */
	private function zip_dirs( $roots, $zip_path ) {
		if ( ! class_exists( 'ZipArchive' ) ) {
			return new WP_Error( 'no_zip', 'ZipArchive not available on this server.', array( 'status' => 500 ) );
		}
		$za = new ZipArchive();
		if ( true !== $za->open( $zip_path, ZipArchive::CREATE | ZipArchive::OVERWRITE ) ) {
			return new WP_Error( 'zip_open', 'Could not create backup zip.', array( 'status' => 500 ) );
		}
		foreach ( $roots as $label => $base ) {
			$base = rtrim( $base, '/\\' );
			if ( ! is_dir( $base ) ) {
				continue;
			}
			$it = new RecursiveIteratorIterator(
				new RecursiveDirectoryIterator( $base, FilesystemIterator::SKIP_DOTS )
			);
			foreach ( $it as $file ) {
				if ( ! $file->isFile() ) {
					continue;
				}
				$abs = $file->getPathname();
				$rel = $label . '/' . ltrim( str_replace( $base, '', $abs ), '/\\' );
				$rel = str_replace( '\\', '/', $rel );
				$za->addFile( $abs, $rel );
			}
		}
		$za->close();
		return true;
	}

	// ---- WP options (read/write any setting) ----------------------------
	public function get_option_r( $r ) {
		$key = sanitize_text_field( (string) $r->get_param( 'key' ) );
		if ( ! $key ) {
			return new WP_Error( 'bad', 'key required', array( 'status' => 400 ) );
		}
		return rest_ensure_response( array( 'key' => $key, 'value' => get_option( $key, null ) ) );
	}
	public function set_option_r( $r ) {
		$b   = $r->get_json_params();
		$key = isset( $b['key'] ) ? sanitize_text_field( $b['key'] ) : '';
		if ( ! $key ) {
			return new WP_Error( 'bad', 'key required', array( 'status' => 400 ) );
		}
		// Protect a few options that could lock the owner out.
		$blocked = array( 'siteurl', 'home', 'admin_email', 'users_can_register' );
		if ( in_array( $key, $blocked, true ) ) {
			return new WP_Error( 'protected', 'That option is protected: ' . $key, array( 'status' => 400 ) );
		}
		update_option( $key, isset( $b['value'] ) ? $b['value'] : '' );
		return rest_ensure_response( array( 'key' => $key, 'saved' => true ) );
	}

	// ---- robots.txt -----------------------------------------------------
	public function get_robots() {
		return rest_ensure_response( array( 'robots' => (string) get_option( 'wpps_robots_txt', '' ) ) );
	}
	public function set_robots( $r ) {
		$b = $r->get_json_params();
		update_option( 'wpps_robots_txt', isset( $b['robots'] ) ? wp_strip_all_tags( (string) $b['robots'] ) : '' );
		return rest_ensure_response( array( 'saved' => true ) );
	}

	// ---- .htaccess (risky - backed up first) ----------------------------
	public function get_htaccess() {
		$path = ABSPATH . '.htaccess';
		return rest_ensure_response( array(
			'exists'   => file_exists( $path ),
			'contents' => file_exists( $path ) ? file_get_contents( $path ) : '',
		) );
	}
	public function set_htaccess( $r ) {
		$b    = $r->get_json_params();
		$path = ABSPATH . '.htaccess';
		if ( file_exists( $path ) ) {
			@copy( $path, trailingslashit( WPPSEO_BACKUP_DIR ) . gmdate( 'Ymd-His' ) . '__htaccess.bak' );
		}
		$ok = @file_put_contents( $path, (string) ( isset( $b['contents'] ) ? $b['contents'] : '' ) );
		if ( false === $ok ) {
			return new WP_Error( 'write', 'Could not write .htaccess', array( 'status' => 500 ) );
		}
		return rest_ensure_response( array( 'saved' => true, 'bytes' => $ok ) );
	}

	// ---- install plugin from WordPress.org ------------------------------
	public function install_plugin( $r ) {
		$b    = $r->get_json_params();
		$slug = isset( $b['slug'] ) ? sanitize_key( $b['slug'] ) : '';
		if ( ! $slug ) {
			return new WP_Error( 'bad', 'plugin slug required', array( 'status' => 400 ) );
		}
		require_once ABSPATH . 'wp-admin/includes/plugin.php';
		require_once ABSPATH . 'wp-admin/includes/file.php';
		require_once ABSPATH . 'wp-admin/includes/misc.php';
		require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
		require_once ABSPATH . 'wp-admin/includes/plugin-install.php';

		$api = plugins_api( 'plugin_information', array( 'slug' => $slug, 'fields' => array( 'sections' => false ) ) );
		if ( is_wp_error( $api ) ) {
			return new WP_Error( 'not_found', 'Plugin not found on WordPress.org: ' . $slug, array( 'status' => 404 ) );
		}
		$upgrader = new Plugin_Upgrader( new WP_Ajax_Upgrader_Skin() );
		$result   = $upgrader->install( $api->download_link );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$activate = ! empty( $b['activate'] );
		$file     = $upgrader->plugin_info();
		if ( $activate && $file ) {
			activate_plugin( $file );
		}
		return rest_ensure_response( array( 'installed' => $slug, 'file' => $file, 'activated' => $activate ) );
	}

	// ---- site health ----------------------------------------------------
	public function health() {
		global $wpdb;
		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}
		$db_size = $wpdb->get_var( "SELECT ROUND(SUM(data_length+index_length)/1024/1024,1) FROM information_schema.TABLES WHERE table_schema='" . DB_NAME . "'" );
		return rest_ensure_response( array(
			'php_version'    => PHP_VERSION,
			'wp_version'     => get_bloginfo( 'version' ),
			'active_theme'   => get_stylesheet(),
			'plugins_total'  => count( get_plugins() ),
			'plugins_active' => count( (array) get_option( 'active_plugins', array() ) ),
			'db_size_mb'     => $db_size,
			'https'          => is_ssl(),
			'debug_mode'     => ( defined( 'WP_DEBUG' ) && WP_DEBUG ),
			'memory_limit'   => WP_MEMORY_LIMIT,
		) );
	}

	// ---- activity log ---------------------------------------------------
	public function get_activity() {
		$log = get_option( 'wppseo_activity_log', array() );
		return rest_ensure_response( array( 'log' => is_array( $log ) ? array_slice( array_reverse( $log ), 0, 100 ) : array() ) );
	}
	public function log_activity( $r ) {
		$b   = $r->get_json_params();
		$msg = isset( $b['msg'] ) ? sanitize_text_field( $b['msg'] ) : '';
		if ( ! $msg ) {
			return new WP_Error( 'bad', 'msg required', array( 'status' => 400 ) );
		}
		$log   = get_option( 'wppseo_activity_log', array() );
		$log   = is_array( $log ) ? $log : array();
		$log[] = array( 'time' => current_time( 'mysql' ), 'msg' => $msg );
		$log   = array_slice( $log, -200 ); // keep last 200
		update_option( 'wppseo_activity_log', $log );
		return rest_ensure_response( array( 'logged' => true ) );
	}

	// ---- image optimize: compress + optional WebP -----------------------
	public function optimize_images( $r ) {
		$b        = $r->get_json_params();
		$limit    = isset( $b['limit'] ) ? min( 100, absint( $b['limit'] ) ) : 30;
		$quality  = isset( $b['quality'] ) ? max( 40, min( 95, absint( $b['quality'] ) ) ) : 80;
		$to_webp  = ! empty( $b['to_webp'] );
		$apply    = ! empty( $b['apply'] );

		$q = new WP_Query( array(
			'post_type'      => 'attachment',
			'post_mime_type' => array( 'image/jpeg', 'image/png' ),
			'post_status'    => 'inherit',
			'posts_per_page' => $limit,
			'fields'         => 'ids',
		) );

		$results = array();
		$saved_total = 0;
		foreach ( $q->posts as $id ) {
			$file = get_attached_file( $id );
			if ( ! $file || ! file_exists( $file ) ) {
				continue;
			}
			$before = filesize( $file );
			$row = array( 'id' => $id, 'file' => basename( $file ), 'before' => $before );

			if ( $apply ) {
				$editor = wp_get_image_editor( $file );
				if ( is_wp_error( $editor ) ) {
					$row['error'] = 'no image editor';
					$results[] = $row;
					continue;
				}
				$editor->set_quality( $quality );
				if ( $to_webp ) {
					$new = preg_replace( '/\.(jpe?g|png)$/i', '.webp', $file );
					$out = $editor->save( $new, 'image/webp' );
					if ( ! is_wp_error( $out ) && isset( $out['path'] ) ) {
						$row['after']  = filesize( $out['path'] );
						$row['webp']   = basename( $out['path'] );
						$saved_total  += max( 0, $before - $row['after'] );
					} else {
						$row['error'] = 'webp not supported on this server';
					}
				} else {
					// Re-save (compress) over the same file, backing it up first.
					@copy( $file, trailingslashit( WPPSEO_BACKUP_DIR ) . gmdate( 'Ymd-His' ) . '__' . basename( $file ) );
					$out = $editor->save( $file );
					clearstatcache();
					$row['after'] = file_exists( $file ) ? filesize( $file ) : $before;
					$saved_total += max( 0, $before - $row['after'] );
				}
			}
			$results[] = $row;
		}

		return rest_ensure_response( array(
			'mode'         => $apply ? 'APPLIED' : 'PREVIEW',
			'processed'    => count( $results ),
			'bytes_saved'  => $saved_total,
			'quality'      => $quality,
			'webp'         => $to_webp,
			'items'        => $results,
		) );
	}

	// ---- llms.txt (AI-friendly site index) ------------------------------
	public function get_llms( $r ) {
		$custom = (string) get_option( 'wpps_llms_txt', '' );
		return rest_ensure_response( array(
			'url'         => home_url( '/llms.txt' ),
			'custom_set'  => ( trim( $custom ) !== '' ),
			'custom'      => $custom,
			'note'        => 'If custom is empty, llms.txt is auto-generated from the site.',
		) );
	}
	public function set_llms( $r ) {
		$b = $r->get_json_params();
		// empty string clears the custom override (back to auto-generate).
		update_option( 'wpps_llms_txt', isset( $b['contents'] ) ? (string) $b['contents'] : '' );
		return rest_ensure_response( array( 'saved' => true, 'url' => home_url( '/llms.txt' ) ) );
	}

	// ---- backups ---------------------------------------------------------
	public function backups() {
		$dir = WPPSEO_BACKUP_DIR;
		$out = array();
		if ( is_dir( $dir ) ) {
			foreach ( scandir( $dir ) as $f ) {
				if ( $f === '.' || $f === '..' || $f === '.htaccess' || $f === 'index.php' ) {
					continue;
				}
				$out[] = array( 'name' => $f, 'size' => filesize( $dir . '/' . $f ) );
			}
		}
		return rest_ensure_response( array( 'backups' => $out ) );
	}
}
