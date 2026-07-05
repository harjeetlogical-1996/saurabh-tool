<?php
/**
 * Plugin Name: wptaskify
 * Plugin URI: https://wptaskify.com
 * Description: Connect your WordPress site to AI (Claude & ChatGPT) and let it manage everything - full SEO (meta, schema, sitemaps, score), custom CSS, designed pages, and safe creation/editing of themes and plugins (with automatic backups and PHP syntax checks).
 * Version: 1.4.1
 * Requires at least: 5.6
 * Requires PHP: 7.4
 * Author: WP Pilot
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: wp-pilot-seo
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // No direct access.
}

define( 'WPPSEO_VERSION', '1.4.1' );
define( 'WPPSEO_FILE', __FILE__ );
define( 'WPPSEO_DIR', plugin_dir_path( __FILE__ ) );
define( 'WPPSEO_URL', plugin_dir_url( __FILE__ ) );
// Studio module: automatic backups before any AI file edit.
define( 'WPPSEO_BACKUP_DIR', WP_CONTENT_DIR . '/wp-pilot-backups' );

/**
 * Meta keys used throughout the plugin (single source of truth).
 * A function (not an array constant) so it works on PHP 5.6+ where
 * indexing a constant array directly is not supported.
 */
function wppseo_meta_keys() {
	return array(
		'title'       => '_wppseo_title',
		'description' => '_wppseo_description',
		'focus_kw'    => '_wppseo_focus_kw',
		'keywords'    => '_wppseo_keywords',
		'og_title'    => '_wppseo_og_title',
		'og_desc'     => '_wppseo_og_desc',
		'og_image'    => '_wppseo_og_image',
		'canonical'   => '_wppseo_canonical',
		'noindex'     => '_wppseo_noindex',
		'schema_type' => '_wppseo_schema_type',
		'faq'         => '_wppseo_faq',
	);
}

/**
 * Get one meta key by short name.
 */
function wppseo_key( $name ) {
	$keys = wppseo_meta_keys();
	return isset( $keys[ $name ] ) ? $keys[ $name ] : $name;
}

// Load modules.
require_once WPPSEO_DIR . 'includes/class-metabox.php';
require_once WPPSEO_DIR . 'includes/class-frontend.php';
require_once WPPSEO_DIR . 'includes/class-schema.php';
require_once WPPSEO_DIR . 'includes/class-sitemap.php';
require_once WPPSEO_DIR . 'includes/class-llms.php';
require_once WPPSEO_DIR . 'includes/class-score.php';
require_once WPPSEO_DIR . 'includes/class-aiseo.php';
require_once WPPSEO_DIR . 'includes/class-rest.php';
require_once WPPSEO_DIR . 'includes/class-updater.php';
require_once WPPSEO_DIR . 'includes/class-admin.php';
// Studio module - CSS, files, theme/plugin build (safe: backups + PHP lint).
require_once WPPSEO_DIR . 'includes/class-studio-fs.php';
require_once WPPSEO_DIR . 'includes/class-studio-rest.php';

/**
 * Boot the plugin.
 */
function wppseo_init() {
	WPPSEO_Metabox::instance();
	WPPSEO_Frontend::instance();
	WPPSEO_Schema::instance();
	WPPSEO_Sitemap::instance();
	WPPSEO_LLMs::instance();
	WPPSEO_REST::instance();
	WPPSEO_Studio_REST::instance(); // CSS + file/theme/plugin build routes
	if ( is_admin() ) {
		WPPSEO_Updater::instance();
		WPPSEO_Admin::instance();
	}
}
add_action( 'plugins_loaded', 'wppseo_init' );

/**
 * Activation: register sitemap rewrite + flush once, and prepare the Studio
 * backup directory (protected from web access).
 */
function wppseo_activate() {
	WPPSEO_Sitemap::add_rewrite();
	WPPSEO_LLMs::add_rewrite();
	flush_rewrite_rules();

	if ( ! file_exists( WPPSEO_BACKUP_DIR ) ) {
		wp_mkdir_p( WPPSEO_BACKUP_DIR );
	}
	$htaccess = WPPSEO_BACKUP_DIR . '/.htaccess';
	if ( ! file_exists( $htaccess ) ) {
		@file_put_contents( $htaccess, "Deny from all\n" );
	}
	$index = WPPSEO_BACKUP_DIR . '/index.php';
	if ( ! file_exists( $index ) ) {
		@file_put_contents( $index, "<?php // Silence is golden.\n" );
	}
}
register_activation_hook( __FILE__, 'wppseo_activate' );

/**
 * Deactivation: clean rewrite rules.
 */
function wppseo_deactivate() {
	flush_rewrite_rules();
}
register_deactivation_hook( __FILE__, 'wppseo_deactivate' );

/**
 * Helper: get a SEO meta value for a post.
 */
function wppseo_get( $post_id, $key, $default = '' ) {
	$meta_key = wppseo_key( $key );
	$val = get_post_meta( $post_id, $meta_key, true );
	return ( '' === $val || null === $val ) ? $default : $val;
}
