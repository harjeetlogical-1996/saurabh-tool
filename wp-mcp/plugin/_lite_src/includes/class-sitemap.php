<?php
/**
 * Simple XML sitemap at /wppseo-sitemap.xml (posts + pages, noindex excluded).
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Sitemap {

	private static $instance = null;
	const SLUG = 'wppseo-sitemap.xml';

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'init', array( __CLASS__, 'add_rewrite' ) );
		add_filter( 'query_vars', array( $this, 'query_var' ) );
		add_action( 'template_redirect', array( $this, 'maybe_render' ) );
		// Tell robots where the sitemap is.
		add_filter( 'robots_txt', array( $this, 'robots' ), 10, 2 );
	}

	public static function add_rewrite() {
		add_rewrite_rule( '^' . self::SLUG . '$', 'index.php?wppseo_sitemap=1', 'top' );
	}

	public function query_var( $vars ) {
		$vars[] = 'wppseo_sitemap';
		return $vars;
	}

	public function robots( $output, $public ) {
		if ( $public ) {
			$output .= "\nSitemap: " . home_url( '/' . self::SLUG ) . "\n";
		}
		return $output;
	}

	public function maybe_render() {
		if ( ! get_query_var( 'wppseo_sitemap' ) ) {
			return;
		}
		header( 'Content-Type: application/xml; charset=UTF-8' );

		$types = get_post_types( array( 'public' => true ), 'names' );
		unset( $types['attachment'] );

		$q = new WP_Query( array(
			'post_type'      => array_values( $types ),
			'post_status'    => 'publish',
			'posts_per_page' => 2000,
			'orderby'        => 'modified',
			'order'          => 'DESC',
			'no_found_rows'  => true,
			'meta_query'     => array(
				'relation' => 'OR',
				array( 'key' => wppseo_key( 'noindex' ), 'value' => '1', 'compare' => '!=' ),
				array( 'key' => wppseo_key( 'noindex' ), 'compare' => 'NOT EXISTS' ),
			),
		) );

		echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
		echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
		// Home.
		echo "  <url><loc>" . esc_url( home_url( '/' ) ) . "</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n";
		while ( $q->have_posts() ) {
			$q->the_post();
			$loc = get_permalink();
			$mod = get_the_modified_date( 'c' );
			echo "  <url><loc>" . esc_url( $loc ) . "</loc><lastmod>" . esc_html( $mod ) . "</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n";
		}
		wp_reset_postdata();
		echo '</urlset>';
		exit;
	}
}
