<?php
/**
 * Plugin Name:       FII Flows
 * Plugin URI:        https://example.com/fii-flows
 * Description:        Daily FII/DII flows, F&O positions, top gainers/losers and a full NSE stocks directory. Auto-fetches free NSE end-of-day data (with GitHub mirror fallback) and serves it via shortcodes with charts. AEO/EEAT friendly.
 * Version:           0.1.0
 * Author:            Saurabh Bhayana
 * License:           GPL-2.0+
 * Text Domain:       fii-flows
 *
 * NOTE: Data is END-OF-DAY (free NSE). Not real-time. See FII-KEYWORD-MAP.md.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // No direct access.
}

define( 'FIIF_VERSION', '0.1.0' );
define( 'FIIF_PATH', plugin_dir_path( __FILE__ ) );
define( 'FIIF_URL', plugin_dir_url( __FILE__ ) );
define( 'FIIF_DB_VERSION', '2' );

// Custom DB table name helper.
function fiif_table( $name ) {
	global $wpdb;
	return $wpdb->prefix . 'fiif_' . $name;
}

// --- Includes ---
require_once FIIF_PATH . 'includes/storage.php';
require_once FIIF_PATH . 'includes/parser.php';
require_once FIIF_PATH . 'includes/fetcher.php';
require_once FIIF_PATH . 'includes/shortcodes.php';
require_once FIIF_PATH . 'includes/admin.php';

/**
 * Activation: create DB tables + schedule cron.
 */
function fiif_activate() {
	fiif_create_tables();

	// Schedule daily fetch at ~20:00 IST (14:30 UTC). WP cron uses site timezone-agnostic UTC under the hood,
	// but we schedule via a near-future timestamp and a daily recurrence; the admin can also Fetch Now.
	if ( ! wp_next_scheduled( 'fiif_daily_fetch' ) ) {
		// Next 20:00 in the site's local time.
		$ts = fiif_next_run_timestamp( 20, 0 );
		wp_schedule_event( $ts, 'daily', 'fiif_daily_fetch' );
	}
}
register_activation_hook( __FILE__, 'fiif_activate' );

/**
 * Deactivation: clear cron (keep data).
 */
function fiif_deactivate() {
	$ts = wp_next_scheduled( 'fiif_daily_fetch' );
	if ( $ts ) {
		wp_unschedule_event( $ts, 'fiif_daily_fetch' );
	}
}
register_deactivation_hook( __FILE__, 'fiif_deactivate' );

/**
 * Compute the next UNIX timestamp for a given local hour:min today/tomorrow.
 */
function fiif_next_run_timestamp( $hour, $min ) {
	$tz   = wp_timezone();
	$now  = new DateTime( 'now', $tz );
	$run  = new DateTime( 'now', $tz );
	$run->setTime( $hour, $min, 0 );
	if ( $run <= $now ) {
		$run->modify( '+1 day' );
	}
	return $run->getTimestamp();
}

/**
 * The cron callback — run the full daily fetch.
 */
add_action( 'fiif_daily_fetch', 'fiif_run_daily_fetch' );
function fiif_run_daily_fetch() {
	fiif_fetch_all(); // defined in fetcher.php
}

/**
 * Make sure tables exist if the plugin was updated without reactivation.
 */
add_action( 'plugins_loaded', function () {
	if ( get_option( 'fiif_db_version' ) !== FIIF_DB_VERSION ) {
		fiif_create_tables();
	}
} );

/**
 * Enqueue front-end assets (Chart.js + our JS/CSS) only when a shortcode is present.
 */
add_action( 'wp_enqueue_scripts', function () {
	global $post;
	if ( ! is_a( $post, 'WP_Post' ) ) {
		return;
	}
	$has_sc = false;
	foreach ( array( 'fii_dii_table', 'fii_dii_chart', 'fii_fno', 'fii_mood', 'top_gainers', 'top_losers', 'most_active', 'stocks_directory', 'fii_stats', 'fii_streak', 'fii_monthly', 'fii_sectors', 'fii_calendar' ) as $sc ) {
		if ( has_shortcode( $post->post_content, $sc ) ) {
			$has_sc = true;
			break;
		}
	}
	if ( ! $has_sc ) {
		return;
	}

	wp_enqueue_style( 'fiif-style', FIIF_URL . 'assets/style.css', array(), FIIF_VERSION );
	wp_enqueue_script( 'fiif-chartjs', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js', array(), '4.4.1', true );
	wp_enqueue_script( 'fiif-charts', FIIF_URL . 'assets/charts.js', array( 'fiif-chartjs' ), FIIF_VERSION, true );
} );
