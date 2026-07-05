<?php
/**
 * SEO meta box on the post/page editor.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Metabox {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'add_meta_boxes', array( $this, 'add_box' ) );
		add_action( 'save_post', array( $this, 'save' ), 10, 2 );
		add_action( 'admin_enqueue_scripts', array( $this, 'assets' ) );
		// Register meta so the Block Editor + REST can see them.
		add_action( 'init', array( $this, 'register_meta' ) );
	}

	public function register_meta() {
		foreach ( wppseo_meta_keys() as $key => $meta_key ) {
			register_post_meta( '', $meta_key, array(
				'show_in_rest'  => true,
				'single'        => true,
				'type'          => 'string',
				'auth_callback' => function () {
					return current_user_can( 'edit_posts' );
				},
			) );
		}
	}

	public function add_box() {
		$types = get_post_types( array( 'public' => true ), 'names' );
		foreach ( $types as $type ) {
			add_meta_box(
				'wppseo_box',
				__( 'WP Pilot SEO', 'wptaskify-seo' ),
				array( $this, 'render' ),
				$type,
				'normal',
				'high'
			);
		}
	}

	public function assets( $hook ) {
		if ( ! in_array( $hook, array( 'post.php', 'post-new.php' ), true ) ) {
			return;
		}
		wp_enqueue_style( 'wppseo-admin', WPPSEO_URL . 'admin.css', array(), WPPSEO_VERSION );
		wp_enqueue_script( 'wppseo-admin', WPPSEO_URL . 'admin.js', array(), WPPSEO_VERSION, true );
	}

	public function render( $post ) {
		wp_nonce_field( 'wppseo_save', 'wppseo_nonce' );
		$v = function ( $key ) use ( $post ) {
			return esc_attr( wppseo_get( $post->ID, $key ) );
		};
		$title    = $v( 'title' );
		$desc     = wppseo_get( $post->ID, 'description' );
		$focus    = $v( 'focus_kw' );
		$keywords = $v( 'keywords' );
		$og_title = $v( 'og_title' );
		$og_desc  = wppseo_get( $post->ID, 'og_desc' );
		$og_image = $v( 'og_image' );
		$canon    = $v( 'canonical' );
		$noindex  = wppseo_get( $post->ID, 'noindex' );
		$stype    = wppseo_get( $post->ID, 'schema_type', 'Article' );

		$schema_opts = array( 'Article', 'BlogPosting', 'NewsArticle', 'Product', 'FAQPage', 'HowTo', 'WebPage' );
		?>
		<div class="wppseo-wrap">
			<div class="wppseo-tabs">
				<button type="button" class="wppseo-tab active" data-tab="general"><?php esc_html_e( 'General', 'wptaskify-seo' ); ?></button>
				<button type="button" class="wppseo-tab" data-tab="social"><?php esc_html_e( 'Social', 'wptaskify-seo' ); ?></button>
				<button type="button" class="wppseo-tab" data-tab="schema"><?php esc_html_e( 'Schema', 'wptaskify-seo' ); ?></button>
				<button type="button" class="wppseo-tab" data-tab="advanced"><?php esc_html_e( 'Advanced', 'wptaskify-seo' ); ?></button>
			</div>

			<div class="wppseo-panel" data-panel="general">
				<div class="wppseo-snippet">
					<div class="wppseo-snippet-title" id="wppseo-prev-title"></div>
					<div class="wppseo-snippet-url"><?php echo esc_html( get_permalink( $post ) ); ?></div>
					<div class="wppseo-snippet-desc" id="wppseo-prev-desc"></div>
				</div>

				<p><label><strong><?php esc_html_e( 'Focus keyword', 'wptaskify-seo' ); ?></strong></label>
				<input type="text" id="wppseo-focus" name="wppseo[focus_kw]" value="<?php echo $focus; ?>" placeholder="<?php esc_attr_e( 'e.g. best water filter', 'wptaskify-seo' ); ?>"></p>

				<p><label><strong><?php esc_html_e( 'SEO title', 'wptaskify-seo' ); ?></strong>
				<span class="wppseo-count" id="wppseo-title-count"></span></label>
				<input type="text" id="wppseo-title" name="wppseo[title]" value="<?php echo $title; ?>"></p>

				<p><label><strong><?php esc_html_e( 'Meta description', 'wptaskify-seo' ); ?></strong>
				<span class="wppseo-count" id="wppseo-desc-count"></span></label>
				<textarea id="wppseo-desc" name="wppseo[description]" rows="3"><?php echo esc_textarea( $desc ); ?></textarea></p>

				<p><label><strong><?php esc_html_e( 'Other keywords', 'wptaskify-seo' ); ?></strong> <em>(<?php esc_html_e( 'comma separated', 'wptaskify-seo' ); ?>)</em></label>
				<input type="text" name="wppseo[keywords]" value="<?php echo $keywords; ?>"></p>

				<div class="wppseo-score" id="wppseo-score">
					<div class="wppseo-score-dot"></div>
					<div class="wppseo-score-text"><?php esc_html_e( 'Enter a focus keyword to see your SEO score.', 'wptaskify-seo' ); ?></div>
				</div>
				<ul class="wppseo-checks" id="wppseo-checks"></ul>
			</div>

			<div class="wppseo-panel" data-panel="social" hidden>
				<p><label><strong><?php esc_html_e( 'Social (OG) title', 'wptaskify-seo' ); ?></strong></label>
				<input type="text" name="wppseo[og_title]" value="<?php echo $og_title; ?>" placeholder="<?php esc_attr_e( 'Defaults to SEO title', 'wptaskify-seo' ); ?>"></p>
				<p><label><strong><?php esc_html_e( 'Social description', 'wptaskify-seo' ); ?></strong></label>
				<textarea name="wppseo[og_desc]" rows="3" placeholder="<?php esc_attr_e( 'Defaults to meta description', 'wptaskify-seo' ); ?>"><?php echo esc_textarea( $og_desc ); ?></textarea></p>
				<p><label><strong><?php esc_html_e( 'Social image URL', 'wptaskify-seo' ); ?></strong></label>
				<input type="url" name="wppseo[og_image]" value="<?php echo $og_image; ?>" placeholder="<?php esc_attr_e( 'Defaults to featured image', 'wptaskify-seo' ); ?>"></p>
			</div>

			<div class="wppseo-panel" data-panel="schema" hidden>
				<p><label><strong><?php esc_html_e( 'Schema type', 'wptaskify-seo' ); ?></strong></label>
				<select name="wppseo[schema_type]">
					<?php foreach ( $schema_opts as $opt ) : ?>
						<option value="<?php echo esc_attr( $opt ); ?>" <?php selected( $stype, $opt ); ?>><?php echo esc_html( $opt ); ?></option>
					<?php endforeach; ?>
				</select></p>
				<p class="description"><?php esc_html_e( 'FAQ items can be managed via the AI assistant or REST API. Article, Breadcrumb & Organization schema are added automatically.', 'wptaskify-seo' ); ?></p>
			</div>

			<div class="wppseo-panel" data-panel="advanced" hidden>
				<p><label><strong><?php esc_html_e( 'Canonical URL', 'wptaskify-seo' ); ?></strong></label>
				<input type="url" name="wppseo[canonical]" value="<?php echo $canon; ?>" placeholder="<?php esc_attr_e( 'Leave blank for default', 'wptaskify-seo' ); ?>"></p>
				<p><label><input type="checkbox" name="wppseo[noindex]" value="1" <?php checked( $noindex, '1' ); ?>> <strong><?php esc_html_e( 'Hide this page from search engines (noindex)', 'wptaskify-seo' ); ?></strong></label></p>
			</div>
		</div>
		<?php
	}

	public function save( $post_id, $post ) {
		if ( ! isset( $_POST['wppseo_nonce'] ) || ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['wppseo_nonce'] ) ), 'wppseo_save' ) ) {
			return;
		}
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}
		if ( empty( $_POST['wppseo'] ) || ! is_array( $_POST['wppseo'] ) ) {
			return;
		}
		$in = wp_unslash( $_POST['wppseo'] );

		$fields = array(
			'title'       => 'sanitize_text_field',
			'description' => 'sanitize_textarea_field',
			'focus_kw'    => 'sanitize_text_field',
			'keywords'    => 'sanitize_text_field',
			'og_title'    => 'sanitize_text_field',
			'og_desc'     => 'sanitize_textarea_field',
			'og_image'    => 'esc_url_raw',
			'canonical'   => 'esc_url_raw',
			'schema_type' => 'sanitize_text_field',
		);
		foreach ( $fields as $key => $sanitizer ) {
			$val = isset( $in[ $key ] ) ? call_user_func( $sanitizer, $in[ $key ] ) : '';
			update_post_meta( $post_id, wppseo_key( $key ), $val );
		}
		update_post_meta( $post_id, wppseo_key( 'noindex' ), empty( $in['noindex'] ) ? '' : '1' );
	}
}
