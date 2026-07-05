<?php
/**
 * ============================================================================
 * DIAGNOSTIC + MIGRATION: theme _cwg_seo_* meta  ->  wptaskify _wppseo_* meta
 * ============================================================================
 * Run ONCE via the "Code Snippets" plugin (recommended) or child-theme
 * functions.php, then REMOVE it. It is safe:
 *   - only FILLS EMPTY plugin fields (never overwrites what you already set)
 *   - runs once (guarded by an option)
 *   - admin-only
 *
 * STEP 1 (diagnostic): First set $DRY_RUN = true below and load any wp-admin
 *   page. You'll get a notice showing HOW MANY posts have each theme key and
 *   how many fields WOULD be copied - WITHOUT changing anything. This confirms
 *   the theme really uses `_cwg_seo_*` keys.
 * STEP 2 (apply): Once the dry-run numbers look right, set $DRY_RUN = false,
 *   load an admin page once, see the "migration complete" notice, then delete
 *   this snippet.
 * ============================================================================
 */

add_action( 'admin_init', function () {

	// ----- CONFIG -----
	$DRY_RUN = true;   // TRUE = just report; FALSE = actually copy.
	// ------------------

	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}
	// Guard: the real (apply) run happens only once.
	if ( ! $DRY_RUN && get_option( 'cwg_seo_migrated_v1' ) === 'done' ) {
		return;
	}

	$map = array(
		'_cwg_seo_title'       => '_wppseo_title',
		'_cwg_seo_description' => '_wppseo_description',
		'_cwg_seo_keywords'    => '_wppseo_keywords',
		'_cwg_seo_focus_kw'    => '_wppseo_focus_kw',
		'_cwg_seo_canonical'   => '_wppseo_canonical',
		'_cwg_seo_og_title'    => '_wppseo_og_title',
		'_cwg_seo_og_desc'     => '_wppseo_og_desc',
		'_cwg_seo_og_image'    => '_wppseo_og_image',
		'_cwg_seo_schema_type' => '_wppseo_schema_type',
		'_cwg_seo_noindex'     => '_wppseo_noindex',
	);

	// Batch through posts so a large site can't hit a memory/time limit.
	$paged   = 1;
	$copied  = 0;
	$per_key = array();  // how many posts actually HAVE each theme key
	$scanned = 0;

	do {
		$q = new WP_Query( array(
			'post_type'      => array( 'post', 'page' ),
			'post_status'    => 'any',
			'posts_per_page' => 200,
			'paged'          => $paged,
			'fields'         => 'ids',
			'no_found_rows'  => true,
		) );
		$ids = $q->posts;
		foreach ( $ids as $pid ) {
			$scanned++;
			foreach ( $map as $from => $to ) {
				$src = get_post_meta( $pid, $from, true );
				if ( '' === $src || null === $src ) {
					continue;
				}
				$per_key[ $from ] = isset( $per_key[ $from ] ) ? $per_key[ $from ] + 1 : 1;

				$existing = get_post_meta( $pid, $to, true );
				if ( '' !== $existing && null !== $existing ) {
					continue; // don't overwrite an existing plugin value
				}
				if ( ! $DRY_RUN ) {
					update_post_meta( $pid, $to, $src );
				}
				$copied++;
			}
		}
		$paged++;
	} while ( ! empty( $ids ) );

	if ( ! $DRY_RUN ) {
		update_option( 'cwg_seo_migrated_v1', 'done' );
	}

	set_transient( 'cwg_seo_migrated_notice', array(
		'dry'     => $DRY_RUN,
		'copied'  => $copied,
		'scanned' => $scanned,
		'per_key' => $per_key,
	), 120 );
} );

// One-time admin notice with the result / dry-run report.
add_action( 'admin_notices', function () {
	$d = get_transient( 'cwg_seo_migrated_notice' );
	if ( false === $d ) {
		return;
	}
	delete_transient( 'cwg_seo_migrated_notice' );
	$head = $d['dry']
		? 'WP Taskify migration DRY-RUN (nothing changed):'
		: 'WP Taskify migration complete:';
	echo '<div class="notice notice-' . ( $d['dry'] ? 'info' : 'success' ) . ' is-dismissible"><p>';
	echo '<strong>' . esc_html( $head ) . '</strong> ';
	echo esc_html( sprintf( '%d fields %s across %d posts scanned.',
		intval( $d['copied'] ),
		$d['dry'] ? 'WOULD be copied' : 'copied',
		intval( $d['scanned'] )
	) );
	if ( ! empty( $d['per_key'] ) ) {
		echo '<br>Theme keys found: ';
		$parts = array();
		foreach ( $d['per_key'] as $k => $n ) {
			$parts[] = esc_html( $k . ' (' . $n . ')' );
		}
		echo implode( ', ', $parts );
	} else {
		echo '<br><em>No _cwg_seo_* theme keys found on any post - check the real key names before applying.</em>';
	}
	echo '</p></div>';
} );
