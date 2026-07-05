<?php
/**
 * Clean up wptaskify SEO data on uninstall.
 */
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

global $wpdb;
// Delete all _wppseo_* post meta (esc_like + prepare for safe LIKE matching).
$like = $wpdb->esc_like( '_wppseo_' ) . '%';
$wpdb->query( $wpdb->prepare( "DELETE FROM {$wpdb->postmeta} WHERE meta_key LIKE %s", $like ) );

// Remove our own options (leave user content alone).
foreach ( array( 'wppseo_connected', 'wppseo_score_history' ) as $opt ) {
	delete_option( $opt );
}
