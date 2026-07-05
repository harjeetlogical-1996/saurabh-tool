<?php
/**
 * Admin UI for wptaskify SEO (free edition): a Dashboard, the AI SEO Score, and an
 * optional "Connect to AI" page that links this site to wptaskify.com so Claude or
 * ChatGPT can manage SEO through the wptaskify connector.
 *
 * This free edition contains SEO features only. File/theme/plugin editing ("Studio")
 * is a wptaskify.com feature and is not part of this plugin.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Admin {

	private static $instance = null;
	const PILOT_URL = 'https://wptaskify.com';

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'admin_menu', array( $this, 'menu' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'assets' ) );
		add_action( 'admin_post_wppseo_connect', array( $this, 'handle_connect' ) );
		add_action( 'admin_post_wppseo_disconnect', array( $this, 'handle_disconnect' ) );
	}

	public function assets( $hook ) {
		if ( strpos( (string) $hook, 'wptaskify-seo' ) === false ) {
			return;
		}
		wp_enqueue_style( 'wptaskify-seo-admin', WPPSEO_URL . 'admin.css', array(), WPPSEO_VERSION );
	}

	public function menu() {
		add_menu_page(
			__( 'wptaskify SEO', 'wptaskify-seo' ),
			__( 'wptaskify SEO', 'wptaskify-seo' ),
			'manage_options',
			'wptaskify-seo',
			array( $this, 'render_dashboard' ),
			'dashicons-chart-line',
			58
		);
		$subs = array(
			array( __( 'Dashboard', 'wptaskify-seo' ), 'wptaskify-seo', array( $this, 'render_dashboard' ) ),
			array( __( 'AI SEO Score', 'wptaskify-seo' ), 'wptaskify-seo-score', array( $this, 'render_score' ) ),
			array( __( 'Connect to AI', 'wptaskify-seo' ), 'wptaskify-seo-connect', array( $this, 'render_connect' ) ),
		);
		foreach ( $subs as $s ) {
			add_submenu_page( 'wptaskify-seo', $s[0], $s[0], 'manage_options', $s[1], $s[2] );
		}
	}

	private function head( $title ) {
		echo '<div class="wrap"><h1>' . esc_html( $title ) . '</h1>';
	}
	private function foot() {
		echo '</div>';
	}

	/** Dashboard: quick status + links. */
	public function render_dashboard() {
		$this->head( __( 'wptaskify SEO', 'wptaskify-seo' ) );
		$connected = get_option( 'wppseo_connected' ) ? true : false;
		echo '<p>' . esc_html__( 'Free, full-featured SEO for WordPress. Set titles, descriptions, focus keywords, schema, Open Graph, and an XML sitemap - with a live SEO score on every post.', 'wptaskify-seo' ) . '</p>';
		echo '<div class="card" style="max-width:640px;padding:6px 20px 16px">';
		echo '<h2>' . esc_html__( 'Get started', 'wptaskify-seo' ) . '</h2><ol>';
		echo '<li>' . esc_html__( 'Edit any post or page - the SEO box appears below the editor with a live snippet preview and score.', 'wptaskify-seo' ) . '</li>';
		echo '<li>' . sprintf(
			/* translators: %s: menu label */
			esc_html__( 'Open %s to see a site-wide AI SEO scorecard.', 'wptaskify-seo' ),
			'<a href="' . esc_url( admin_url( 'admin.php?page=wptaskify-seo-score' ) ) . '"><strong>' . esc_html__( 'AI SEO Score', 'wptaskify-seo' ) . '</strong></a>'
		) . '</li>';
		echo '<li>' . sprintf(
			/* translators: %s: menu label */
			esc_html__( 'Optional: %s to let Claude or ChatGPT manage your SEO for you.', 'wptaskify-seo' ),
			'<a href="' . esc_url( admin_url( 'admin.php?page=wptaskify-seo-connect' ) ) . '"><strong>' . esc_html__( 'Connect to AI', 'wptaskify-seo' ) . '</strong></a>'
		) . '</li>';
		echo '</ol>';
		echo '<p>' . ( $connected
			? '<span style="color:#008a20">&#10003; ' . esc_html__( 'Connected to wptaskify.', 'wptaskify-seo' ) . '</span>'
			: esc_html__( 'Not connected to AI yet (optional).', 'wptaskify-seo' ) ) . '</p>';
		echo '</div>';
		$this->foot();
	}

	/** AI SEO Score: site-wide scorecard from the site's own content. */
	public function render_score() {
		$this->head( __( 'AI SEO Score', 'wptaskify-seo' ) );
		if ( class_exists( 'WPPSEO_AiSeo' ) && method_exists( 'WPPSEO_AiSeo', 'score' ) ) {
			$data = WPPSEO_AiSeo::score();
			$overall = isset( $data['overall'] ) ? (int) $data['overall'] : 0;
			echo '<div class="card" style="max-width:720px;padding:6px 20px 20px">';
			echo '<h2 style="font-size:2.4em;margin:10px 0 0">' . esc_html( $overall ) . '<span style="font-size:.4em;color:#646970">/100</span></h2>';
			echo '<p style="color:#646970;margin-top:0">' . esc_html__( 'Overall AI SEO score, measured from your published content.', 'wptaskify-seo' ) . '</p>';
			if ( ! empty( $data['categories'] ) && is_array( $data['categories'] ) ) {
				echo '<table class="widefat striped" style="margin-top:12px"><tbody>';
				foreach ( $data['categories'] as $name => $val ) {
					echo '<tr><td>' . esc_html( ucwords( str_replace( '_', ' ', (string) $name ) ) ) . '</td><td style="text-align:right"><strong>' . esc_html( (int) $val ) . '</strong>/100</td></tr>';
				}
				echo '</tbody></table>';
			}
			if ( isset( $data['posts_scored'] ) ) {
				echo '<p style="margin-top:14px;color:#646970">' . sprintf(
					/* translators: %d: number of posts */
					esc_html__( 'Scored %d published posts.', 'wptaskify-seo' ),
					(int) $data['posts_scored']
				) . '</p>';
			}
			echo '</div>';
		} else {
			echo '<p>' . esc_html__( 'Publish some content to see your AI SEO score.', 'wptaskify-seo' ) . '</p>';
		}
		$this->foot();
	}

	/** Connect to AI: link this site to wptaskify.com (optional). */
	public function render_connect() {
		$this->head( __( 'Connect to AI', 'wptaskify-seo' ) );
		$connected = get_option( 'wppseo_connected' ) ? true : false;
		echo '<div class="card" style="max-width:680px;padding:6px 20px 18px">';
		echo '<p>' . esc_html__( 'Connect this site to wptaskify to let Claude or ChatGPT read and update your SEO through a secure connector. You bring your own AI account - there is no extra AI subscription.', 'wptaskify-seo' ) . '</p>';
		echo '<p>' . sprintf(
			/* translators: %s: external link */
			esc_html__( 'Connecting sends your site URL and a WordPress Application Password to %s so it can act on your behalf. See their privacy policy for details. You can disconnect any time.', 'wptaskify-seo' ),
			'<a href="' . esc_url( self::PILOT_URL . '/privacy' ) . '" target="_blank" rel="noopener">wptaskify.com</a>'
		) . '</p>';

		if ( $connected ) {
			echo '<p style="color:#008a20">&#10003; ' . esc_html__( 'This site is connected to wptaskify.', 'wptaskify-seo' ) . '</p>';
			echo '<form method="post" action="' . esc_url( admin_url( 'admin-post.php' ) ) . '">';
			wp_nonce_field( 'wppseo_disconnect' );
			echo '<input type="hidden" name="action" value="wppseo_disconnect">';
			echo '<button type="submit" class="button">' . esc_html__( 'Disconnect', 'wptaskify-seo' ) . '</button>';
			echo '</form>';
		} else {
			echo '<form method="post" action="' . esc_url( admin_url( 'admin-post.php' ) ) . '">';
			wp_nonce_field( 'wppseo_connect' );
			echo '<input type="hidden" name="action" value="wppseo_connect">';
			echo '<button type="submit" class="button button-primary">' . esc_html__( 'Connect to wptaskify', 'wptaskify-seo' ) . '</button>';
			echo '</form>';
		}
		echo '</div>';
		$this->foot();
	}

	/** Create an Application Password for this admin and hand off to wptaskify. */
	public function handle_connect() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Permission denied.', 'wptaskify-seo' ) );
		}
		check_admin_referer( 'wppseo_connect' );

		if ( ! function_exists( 'wp_create_application_password' ) ) {
			wp_safe_redirect( admin_url( 'admin.php?page=wptaskify-seo-connect&connect_err=app_passwords_unavailable' ) );
			exit;
		}
		$user    = wp_get_current_user();
		$created = wp_create_application_password( $user->ID, array( 'name' => 'wptaskify' ) );
		if ( is_wp_error( $created ) || empty( $created[0] ) ) {
			wp_safe_redirect( admin_url( 'admin.php?page=wptaskify-seo-connect&connect_err=create_failed' ) );
			exit;
		}
		$app_pw = $created[0]; // plaintext, shown once

		update_option( 'wppseo_connected', 1 );

		$return = admin_url( 'admin.php?page=wptaskify-seo-connect&connected=1' );
		$args   = array(
			'site'   => home_url(),
			'user'   => $user->user_login,
			'pw'     => $app_pw,
			'email'  => $user->user_email,
			'return' => $return,
		);
		$url = self::PILOT_URL . '/connect?' . http_build_query( $args );
		wp_redirect( $url );
		exit;
	}

	public function handle_disconnect() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Permission denied.', 'wptaskify-seo' ) );
		}
		check_admin_referer( 'wppseo_disconnect' );

		wp_remote_get(
			self::PILOT_URL . '/disconnect?' . http_build_query( array( 'site' => home_url() ) ),
			array( 'timeout' => 10 )
		);
		delete_option( 'wppseo_connected' );
		wp_safe_redirect( admin_url( 'admin.php?page=wptaskify-seo-connect&disconnected=1' ) );
		exit;
	}
}
