<?php
/**
 * Frontend <head> output: title, meta description, canonical, robots,
 * Open Graph and Twitter Card tags.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Frontend {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		// Let us control the document title.
		add_filter( 'pre_get_document_title', array( $this, 'doc_title' ), 20 );
		add_theme_support( 'title-tag' );
		add_action( 'wp_head', array( $this, 'output' ), 1 );
		// Remove core's default robots so ours wins when set.
	}

	private function resolved_title( $post_id ) {
		$t = $post_id ? wppseo_get( $post_id, 'title' ) : '';
		if ( $t ) {
			return $t;
		}
		if ( is_singular() ) {
			return get_the_title( $post_id ) . ' - ' . get_bloginfo( 'name' );
		}
		return get_bloginfo( 'name' );
	}

	private function resolved_desc( $post_id ) {
		$d = $post_id ? wppseo_get( $post_id, 'description' ) : '';
		if ( $d ) {
			return $d;
		}
		if ( is_singular() && $post_id ) {
			$excerpt = get_the_excerpt( $post_id );
			if ( $excerpt ) {
				return wp_trim_words( wp_strip_all_tags( $excerpt ), 30 );
			}
		}
		return get_bloginfo( 'description' );
	}

	public function doc_title( $title ) {
		$post_id = is_singular() ? get_queried_object_id() : 0;
		$custom  = $post_id ? wppseo_get( $post_id, 'title' ) : '';
		return $custom ? $custom : $title;
	}

	public function output() {
		$post_id = is_singular() ? get_queried_object_id() : 0;
		$title   = $this->resolved_title( $post_id );
		$desc    = $this->resolved_desc( $post_id );
		if ( is_singular() ) {
			$url = get_permalink( $post_id );
		} else {
			$req = isset( $GLOBALS['wp']->request ) ? $GLOBALS['wp']->request : '';
			$url = home_url( $req ? '/' . $req : '/' );
		}

		echo "\n<!-- wptaskify -->\n";

		// Meta description.
		if ( $desc ) {
			printf( "<meta name=\"description\" content=\"%s\">\n", esc_attr( $desc ) );
		}

		// Robots (noindex).
		$noindex = $post_id ? wppseo_get( $post_id, 'noindex' ) : '';
		$robots  = $noindex ? 'noindex, follow' : 'index, follow, max-image-preview:large';
		printf( "<meta name=\"robots\" content=\"%s\">\n", esc_attr( $robots ) );

		// Canonical.
		$canon = $post_id ? wppseo_get( $post_id, 'canonical' ) : '';
		if ( ! $canon ) {
			$canon = $url;
		}
		printf( "<link rel=\"canonical\" href=\"%s\">\n", esc_url( $canon ) );

		// Keywords (optional, low SEO weight but user asked for it).
		$kw = $post_id ? wppseo_get( $post_id, 'keywords' ) : '';
		$focus = $post_id ? wppseo_get( $post_id, 'focus_kw' ) : '';
		$kw_all = trim( $focus . ( $focus && $kw ? ', ' : '' ) . $kw );
		if ( $kw_all ) {
			printf( "<meta name=\"keywords\" content=\"%s\">\n", esc_attr( $kw_all ) );
		}

		// Open Graph.
		$og_title = $post_id ? wppseo_get( $post_id, 'og_title' ) : '';
		$og_desc  = $post_id ? wppseo_get( $post_id, 'og_desc' ) : '';
		$og_img   = $post_id ? wppseo_get( $post_id, 'og_image' ) : '';
		if ( ! $og_img && $post_id && has_post_thumbnail( $post_id ) ) {
			$og_img = get_the_post_thumbnail_url( $post_id, 'large' );
		}
		$og_title = $og_title ? $og_title : $title;
		$og_desc  = $og_desc ? $og_desc : $desc;

		printf( "<meta property=\"og:locale\" content=\"%s\">\n", esc_attr( get_locale() ) );
		printf( "<meta property=\"og:type\" content=\"%s\">\n", is_singular() ? 'article' : 'website' );
		printf( "<meta property=\"og:title\" content=\"%s\">\n", esc_attr( $og_title ) );
		if ( $og_desc ) {
			printf( "<meta property=\"og:description\" content=\"%s\">\n", esc_attr( $og_desc ) );
		}
		printf( "<meta property=\"og:url\" content=\"%s\">\n", esc_url( $url ) );
		printf( "<meta property=\"og:site_name\" content=\"%s\">\n", esc_attr( get_bloginfo( 'name' ) ) );
		if ( $og_img ) {
			printf( "<meta property=\"og:image\" content=\"%s\">\n", esc_url( $og_img ) );
		}

		// Twitter.
		printf( "<meta name=\"twitter:card\" content=\"%s\">\n", $og_img ? 'summary_large_image' : 'summary' );
		printf( "<meta name=\"twitter:title\" content=\"%s\">\n", esc_attr( $og_title ) );
		if ( $og_desc ) {
			printf( "<meta name=\"twitter:description\" content=\"%s\">\n", esc_attr( $og_desc ) );
		}
		if ( $og_img ) {
			printf( "<meta name=\"twitter:image\" content=\"%s\">\n", esc_url( $og_img ) );
		}

		echo "<!-- /wptaskify -->\n";
	}
}
