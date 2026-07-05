<?php
/**
 * JSON-LD structured data output (@graph): Organization, WebSite,
 * BreadcrumbList, and per-post Article/Product/FAQPage/HowTo.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Schema {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'wp_head', array( $this, 'output' ), 5 );
	}

	public function output() {
		$graph = array();
		$home  = home_url( '/' );
		$site  = get_bloginfo( 'name' );

		// Organization.
		$org = array(
			'@type' => 'Organization',
			'@id'   => $home . '#organization',
			'name'  => $site,
			'url'   => $home,
		);
		$logo_id = get_theme_mod( 'custom_logo' );
		if ( $logo_id ) {
			$logo = wp_get_attachment_image_url( $logo_id, 'full' );
			if ( $logo ) {
				$org['logo'] = $logo;
			}
		}
		$graph[] = $org;

		// WebSite.
		$graph[] = array(
			'@type'     => 'WebSite',
			'@id'       => $home . '#website',
			'url'       => $home,
			'name'      => $site,
			'publisher' => array( '@id' => $home . '#organization' ),
		);

		if ( is_singular() ) {
			$post_id = get_queried_object_id();
			$graph   = array_merge( $graph, $this->singular_graph( $post_id, $home ) );
		}

		$data = array(
			'@context' => 'https://schema.org',
			'@graph'   => $graph,
		);

		echo "<script type=\"application/ld+json\">" .
			wp_json_encode( $data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) .
			"</script>\n";
	}

	private function singular_graph( $post_id, $home ) {
		$out  = array();
		$url  = get_permalink( $post_id );
		$type = wppseo_get( $post_id, 'schema_type', 'Article' );

		// Breadcrumb.
		$crumbs = array(
			array( '@type' => 'ListItem', 'position' => 1, 'name' => 'Home', 'item' => $home ),
			array( '@type' => 'ListItem', 'position' => 2, 'name' => get_the_title( $post_id ), 'item' => $url ),
		);
		$out[] = array(
			'@type'           => 'BreadcrumbList',
			'@id'             => $url . '#breadcrumb',
			'itemListElement' => $crumbs,
		);

		// Main entity (Article-like by default).
		$author_id = get_post_field( 'post_author', $post_id );
		$main = array(
			'@type'         => $type,
			'@id'           => $url . '#main',
			'headline'      => get_the_title( $post_id ),
			'url'           => $url,
			'datePublished' => get_the_date( 'c', $post_id ),
			'dateModified'  => get_the_modified_date( 'c', $post_id ),
			'author'        => array( '@type' => 'Person', 'name' => get_the_author_meta( 'display_name', $author_id ) ),
			'publisher'     => array( '@id' => $home . '#organization' ),
			'mainEntityOfPage' => array( '@type' => 'WebPage', '@id' => $url ),
		);
		$desc = wppseo_get( $post_id, 'description' );
		if ( $desc ) {
			$main['description'] = $desc;
		}
		if ( has_post_thumbnail( $post_id ) ) {
			$main['image'] = get_the_post_thumbnail_url( $post_id, 'large' );
		}
		// FAQPage handled separately below; if type is FAQPage, attach questions.
		if ( 'FAQPage' === $type ) {
			$faq = $this->faq_items( $post_id );
			if ( $faq ) {
				$main['mainEntity'] = $faq;
			}
		}
		$out[] = $main;

		// Always also emit FAQ if items exist (even if main type isn't FAQPage).
		if ( 'FAQPage' !== $type ) {
			$faq = $this->faq_items( $post_id );
			if ( $faq ) {
				$out[] = array(
					'@type'      => 'FAQPage',
					'@id'        => $url . '#faq',
					'mainEntity' => $faq,
				);
			}
		}

		return $out;
	}

	/**
	 * FAQ items stored as JSON in the _wppseo_faq meta:
	 * [{"q":"Question?","a":"Answer."}, ...]
	 */
	private function faq_items( $post_id ) {
		$raw = wppseo_get( $post_id, 'faq' );
		if ( ! $raw ) {
			return array();
		}
		$items = json_decode( $raw, true );
		if ( ! is_array( $items ) ) {
			return array();
		}
		$out = array();
		foreach ( $items as $it ) {
			if ( empty( $it['q'] ) || empty( $it['a'] ) ) {
				continue;
			}
			$out[] = array(
				'@type'          => 'Question',
				'name'           => wp_strip_all_tags( $it['q'] ),
				'acceptedAnswer' => array(
					'@type' => 'Answer',
					'text'  => wp_kses_post( $it['a'] ),
				),
			);
		}
		return $out;
	}
}
