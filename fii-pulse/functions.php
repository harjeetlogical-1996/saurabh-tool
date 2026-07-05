<?php
/**
 * FII Pulse theme functions.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'FP_VERSION', '1.0.0' );

/* ---------------- SETUP ---------------- */
add_action( 'after_setup_theme', function () {
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'html5', array( 'search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script' ) );
	add_theme_support( 'automatic-feed-links' );
	add_theme_support( 'custom-logo' );

	register_nav_menus( array(
		'primary' => 'Primary Menu',
		'footer'  => 'Footer Menu',
	) );
} );

/* ---------------- ASSETS ---------------- */
add_action( 'wp_enqueue_scripts', function () {
	wp_enqueue_style( 'fp-style', get_stylesheet_uri(), array(), FP_VERSION );
	wp_enqueue_script( 'fp-main', get_template_directory_uri() . '/assets/main.js', array(), FP_VERSION, true );
} );

/* ---------------- LIVE DATA HELPERS (read from plugin) ---------------- */

/** Is the FII Flows plugin active and has data? */
function fp_has_plugin() {
	return function_exists( 'fiif_get_latest_flow' );
}

/** Latest flow row or null. */
function fp_latest_flow() {
	return fp_has_plugin() ? fiif_get_latest_flow() : null;
}

/** Compute the current mood label + class. */
function fp_mood() {
	if ( ! fp_has_plugin() ) {
		return array( 'Neutral', '' );
	}
	$flow = fiif_get_latest_flow();
	$fno  = function_exists( 'fiif_get_latest_fno' ) ? fiif_get_latest_fno() : null;
	$score = 0;
	if ( $flow ) { $score += $flow->fii_net > 0 ? 1 : -1; }
	if ( $fno && $fno->long_short_ratio > 0 ) { $score += $fno->long_short_ratio > 1 ? 1 : -1; }
	if ( $score >= 1 ) { return array( 'Bullish', 'up' ); }
	if ( $score <= -1 ) { return array( 'Bearish', 'down' ); }
	return array( 'Neutral', '' );
}

/** Format ₹ crore with sign. */
function fp_cr( $n ) {
	$n = (float) $n;
	$sign = $n > 0 ? '+' : ( $n < 0 ? '−' : '' );
	return $sign . '₹' . number_format( abs( $n ), 0 ) . ' Cr';
}

/** Up/down css class from a number. */
function fp_dir_class( $n ) {
	return $n > 0 ? 'up' : ( $n < 0 ? 'down' : '' );
}

/* ---------------- SVG ICONS (Lucide-style, no emojis) ---------------- */
function fp_icon( $name, $size = 20 ) {
	$paths = array(
		'trending-up'   => '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline>',
		'trending-down' => '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"></polyline><polyline points="16 17 22 17 22 11"></polyline>',
		'activity'      => '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>',
		'bar-chart'     => '<line x1="12" y1="20" x2="12" y2="10"></line><line x1="18" y1="20" x2="18" y2="4"></line><line x1="6" y1="20" x2="6" y2="16"></line>',
		'pie-chart'     => '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path><path d="M22 12A10 10 0 0 0 12 2v10z"></path>',
		'calendar'      => '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line>',
		'layers'        => '<polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline>',
		'gauge'         => '<path d="M12 14 4 6"></path><circle cx="12" cy="14" r="8"></circle><path d="M12 2v2M2 14h2M20 14h2"></path>',
		'flame'         => '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path>',
		'help'          => '<circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line>',
		'book'          => '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>',
		'arrow-right'   => '<line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline>',
		'globe'         => '<circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>',
	);
	$p = isset( $paths[ $name ] ) ? $paths[ $name ] : '';
	return '<svg class="fp-i" width="' . (int) $size . '" height="' . (int) $size . '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' . $p . '</svg>';
}

/* ---------------- FALLBACK MENU ---------------- */
function fp_fallback_menu() {
	$items = array(
		'/fii-dii-data/' => 'FII/DII Data',
		'/fii-fno-data/' => 'F&O Data',
		'/top-gainers/'  => 'Top Gainers',
		'/top-losers/'   => 'Top Losers',
		'/stocks/'       => 'Stocks',
	);
	echo '<ul>';
	foreach ( $items as $url => $label ) {
		$cur = ( trim( $_SERVER['REQUEST_URI'], '/' ) === trim( $url, '/' ) ) ? ' class="current-menu-item"' : '';
		echo '<li' . $cur . '><a href="' . esc_url( home_url( $url ) ) . '">' . esc_html( $label ) . '</a></li>';
	}
	echo '</ul>';
}

/* ---------------- SEO / AEO: JSON-LD SCHEMA ---------------- */
add_action( 'wp_head', function () {
	$site = get_bloginfo( 'name' ) ?: 'FII Pulse';
	$url  = home_url( '/' );

	// Organization + WebSite (sitewide).
	$org = array(
		'@context'    => 'https://schema.org',
		'@type'       => 'Organization',
		'name'        => $site,
		'url'         => $url,
		'description' => 'Daily FII/DII flows, F&O positions and stock market data from NSE.',
	);
	echo "\n<script type=\"application/ld+json\">" . wp_json_encode( $org ) . "</script>\n";

	// FAQ schema only on the front page (mirrors the visible FAQ).
	if ( is_front_page() ) {
		$faqs = array(
			array( 'What does "FII net" mean?', 'FII net = FII gross buy minus FII gross sell for the day, in rupees crore. Positive means FIIs bought more than they sold (bullish); negative means they sold more (bearish).' ),
			array( 'Is FII/DII data real-time?', 'No. FII/DII activity is published by NSE after market close each trading day. This site updates automatically every evening with the latest official end-of-day figures.' ),
			array( 'Why do FIIs matter so much?', 'FIIs control a large share of free-float in Indian large-caps. When they buy or sell in size, indices like the Nifty often move with them, which is why their flows are watched closely.' ),
			array( 'What is the FII long/short ratio?', 'In F&O it compares FII long positions to short positions. Above 1 means net long (bullish bias); below 1 means net short (bearish bias).' ),
		);
		$items = array();
		foreach ( $faqs as $f ) {
			$items[] = array(
				'@type'          => 'Question',
				'name'           => $f[0],
				'acceptedAnswer' => array( '@type' => 'Answer', 'text' => $f[1] ),
			);
		}
		$faq_schema = array(
			'@context'   => 'https://schema.org',
			'@type'      => 'FAQPage',
			'mainEntity' => $items,
		);
		echo '<script type="application/ld+json">' . wp_json_encode( $faq_schema ) . "</script>\n";
	}
} );

/* Let AI crawlers in (AEO). */
add_filter( 'robots_txt', function ( $output ) {
	$output .= "\n# Allow AI/search crawlers\n";
	foreach ( array( 'GPTBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended', 'OAI-SearchBot', 'Amazonbot', 'Bingbot' ) as $bot ) {
		$output .= "User-agent: $bot\nAllow: /\n\n";
	}
	return $output;
}, 10, 1 );

/* ---------------- ADSENSE SLOT (optional) ---------------- */
function fp_ad_slot( $id = 'inline' ) {
	$code = get_option( 'fp_adsense_' . $id, '' );
	if ( $code ) {
		echo '<div class="fp-ad fp-ad-' . esc_attr( $id ) . '">' . $code . '</div>';
	}
}
