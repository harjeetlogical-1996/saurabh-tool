<?php
/**
 * REST API so the wptaskify MCP server (AI assistant) can read & write all SEO
 * fields, manage FAQ items, and fetch the SEO score.
 *
 * Namespace: wppseo/v1
 *   GET  /seo?post=ID            -> all SEO fields + score
 *   POST /seo                    -> {post, fields:{...}} update fields
 *   GET  /score?post=ID          -> SEO score + checks
 *   POST /faq                    -> {post, items:[{q,a}]} set FAQ
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_REST {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'rest_api_init', array( $this, 'routes' ) );
	}

	public function perm() {
		return current_user_can( 'edit_posts' );
	}

	public function routes() {
		$ns = 'wppseo/v1';

		register_rest_route( $ns, '/seo', array(
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_seo' ),
				'permission_callback' => array( $this, 'perm' ),
				'args'                => array( 'post' => array( 'required' => true, 'sanitize_callback' => 'absint' ) ),
			),
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'set_seo' ),
				'permission_callback' => array( $this, 'perm' ),
			),
		) );

		register_rest_route( $ns, '/score', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'get_score' ),
			'permission_callback' => array( $this, 'perm' ),
			'args'                => array( 'post' => array( 'required' => true, 'sanitize_callback' => 'absint' ) ),
		) );

		register_rest_route( $ns, '/faq', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'set_faq' ),
			'permission_callback' => array( $this, 'perm' ),
		) );

		register_rest_route( $ns, '/info', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'info' ),
			'permission_callback' => array( $this, 'perm' ),
		) );
	}

	/** Capability discovery for the MCP server. */
	public function info() {
		return array(
			'plugin'  => 'wptaskify-seo',
			'version' => WPPSEO_VERSION,
			'fields'  => array_keys( wppseo_meta_keys() ),
			'sitemap' => home_url( '/' . WPPSEO_Sitemap::SLUG ),
		);
	}

	public function get_seo( $request ) {
		$post_id = $request->get_param( 'post' );
		if ( ! get_post( $post_id ) ) {
			return new WP_Error( 'not_found', 'Post not found', array( 'status' => 404 ) );
		}
		$out = array( 'post' => $post_id );
		foreach ( wppseo_meta_keys() as $key => $meta_key ) {
			$out[ $key ] = wppseo_get( $post_id, $key );
		}
		$out['score'] = WPPSEO_Score::analyze( $post_id );
		return rest_ensure_response( $out );
	}

	public function set_seo( $request ) {
		$body    = $request->get_json_params();
		$post_id = isset( $body['post'] ) ? absint( $body['post'] ) : 0;
		$fields  = isset( $body['fields'] ) && is_array( $body['fields'] ) ? $body['fields'] : array();
		if ( ! $post_id || ! get_post( $post_id ) ) {
			return new WP_Error( 'bad_post', 'Valid post id required', array( 'status' => 400 ) );
		}
		// IDOR guard: caller must be able to edit THIS specific post, not just have the
		// global edit_posts capability (which would let an Author edit others' SEO).
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return new WP_Error( 'forbidden', 'You cannot edit this post.', array( 'status' => 403 ) );
		}

		$allowed = array(
			'title'       => 'sanitize_text_field',
			'description' => 'sanitize_textarea_field',
			'focus_kw'    => 'sanitize_text_field',
			'keywords'    => 'sanitize_text_field',
			'og_title'    => 'sanitize_text_field',
			'og_desc'     => 'sanitize_textarea_field',
			'og_image'    => 'esc_url_raw',
			'canonical'   => 'esc_url_raw',
			'schema_type' => 'sanitize_text_field',
			'noindex'     => 'sanitize_text_field',
		);
		$updated = array();
		foreach ( $fields as $key => $val ) {
			if ( ! isset( $allowed[ $key ] ) ) {
				continue;
			}
			$clean = call_user_func( $allowed[ $key ], $val );
			update_post_meta( $post_id, wppseo_key( $key ), $clean );
			$updated[ $key ] = $clean;
		}
		return rest_ensure_response( array(
			'post'    => $post_id,
			'updated' => $updated,
			'score'   => WPPSEO_Score::analyze( $post_id ),
		) );
	}

	public function get_score( $request ) {
		$post_id = $request->get_param( 'post' );
		if ( ! get_post( $post_id ) ) {
			return new WP_Error( 'not_found', 'Post not found', array( 'status' => 404 ) );
		}
		return rest_ensure_response( WPPSEO_Score::analyze( $post_id ) );
	}

	public function set_faq( $request ) {
		$body    = $request->get_json_params();
		$post_id = isset( $body['post'] ) ? absint( $body['post'] ) : 0;
		$items   = isset( $body['items'] ) && is_array( $body['items'] ) ? $body['items'] : array();
		if ( ! $post_id || ! get_post( $post_id ) ) {
			return new WP_Error( 'bad_post', 'Valid post id required', array( 'status' => 400 ) );
		}
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return new WP_Error( 'forbidden', 'You cannot edit this post.', array( 'status' => 403 ) );
		}
		// Cap FAQ item count + answer length (prevent bloat / DoS - LOW finding #16).
		if ( count( $items ) > 50 ) {
			$items = array_slice( $items, 0, 50 );
		}
		$clean = array();
		foreach ( $items as $it ) {
			if ( empty( $it['q'] ) || empty( $it['a'] ) ) {
				continue;
			}
			$clean[] = array(
				'q' => sanitize_text_field( $it['q'] ),
				'a' => wp_kses_post( $it['a'] ),
			);
		}
		update_post_meta( $post_id, wppseo_key( 'faq' ), wp_json_encode( $clean ) );
		return rest_ensure_response( array( 'post' => $post_id, 'faq_count' => count( $clean ) ) );
	}
}
