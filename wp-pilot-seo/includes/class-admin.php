<?php
/**
 * Admin menu page: onboarding / getting started + a "check for updates" button.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Admin {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	const PILOT_URL = 'https://wptaskify.com';

	private function __construct() {
		add_action( 'admin_menu', array( $this, 'menu' ) );
		add_action( 'admin_post_wppseo_check_update', array( $this, 'handle_check_update' ) );
		add_action( 'admin_post_wppseo_connect', array( $this, 'handle_connect' ) );
		add_action( 'admin_post_wppseo_disconnect', array( $this, 'handle_disconnect' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'assets' ) );
	}

	/**
	 * One-click connect: create an Application Password for this admin, then
	 * hand it off to wptaskify which logs the user in and stores the site.
	 */
	public function handle_connect() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Not allowed', 'wp-pilot-seo' ) );
		}
		check_admin_referer( 'wppseo_connect' );

		if ( ! class_exists( 'WP_Application_Passwords' ) ) {
			wp_safe_redirect( admin_url( 'admin.php?page=wp-pilot-seo&connect_err=app_passwords_unavailable' ) );
			exit;
		}

		$user = wp_get_current_user();
		// Remove an old wptaskify password if present (avoid duplicates).
		$existing = WP_Application_Passwords::get_user_application_passwords( $user->ID );
		foreach ( (array) $existing as $item ) {
			if ( isset( $item['name'] ) && 'WP Pilot' === $item['name'] ) {
				WP_Application_Passwords::delete_application_password( $user->ID, $item['uuid'] );
			}
		}

		$created = WP_Application_Passwords::create_new_application_password(
			$user->ID,
			array( 'name' => 'WP Pilot' )
		);
		if ( is_wp_error( $created ) ) {
			wp_safe_redirect( admin_url( 'admin.php?page=wp-pilot-seo&connect_err=create_failed' ) );
			exit;
		}
		$app_pw = $created[0]; // plaintext, shown once

		// Hand off to wptaskify. It will log the user in / sign up, then store the site.
		$return = admin_url( 'admin.php?page=wp-pilot-seo&connected=1' );
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
			wp_die( esc_html__( 'Not allowed', 'wp-pilot-seo' ) );
		}
		check_admin_referer( 'wppseo_disconnect' );
		$user = wp_get_current_user();
		if ( class_exists( 'WP_Application_Passwords' ) ) {
			$existing = WP_Application_Passwords::get_user_application_passwords( $user->ID );
			foreach ( (array) $existing as $item ) {
				if ( isset( $item['name'] ) && 'WP Pilot' === $item['name'] ) {
					WP_Application_Passwords::delete_application_password( $user->ID, $item['uuid'] );
				}
			}
		}
		// Tell wptaskify to remove this site from its side too - otherwise the
		// server would still report "connected" and the badge would come back.
		wp_remote_get(
			self::PILOT_URL . '/disconnect?' . http_build_query( array( 'site' => home_url() ) ),
			array( 'timeout' => 8 )
		);
		delete_option( 'wppseo_connected' );
		delete_transient( 'wppseo_conn_state' ); // clear the 60s verify cache
		wp_safe_redirect( admin_url( 'admin.php?page=wp-pilot-seo&disconnected=1' ) );
		exit;
	}

	/**
	 * VERIFY the connection with wptaskify instead of trusting a local flag.
	 * A failed connect can still bounce back with ?connected=1, so we ask the
	 * server whether this exact site is really registered. Cached 60s.
	 *
	 * Returns array: connected (bool), dashboard_url (string), reachable (bool).
	 */
	private function connection_state() {
		$cached = get_transient( 'wppseo_conn_state' );
		if ( is_array( $cached ) ) {
			return $cached;
		}
		$url   = self::PILOT_URL . '/connect-status?' . http_build_query( array( 'site' => home_url() ) );
		$resp  = wp_remote_get( $url, array( 'timeout' => 8 ) );
		$state = array(
			'connected'     => false,
			'dashboard_url' => self::PILOT_URL . '/dashboard',
			'reachable'     => true,
		);
		if ( is_wp_error( $resp ) ) {
			// Can't reach wptaskify - fall back to last known flag, don't lie.
			$state['reachable'] = false;
			$state['connected'] = (bool) get_option( 'wppseo_connected' );
			return $state; // don't cache an unreachable result
		}
		$data = json_decode( wp_remote_retrieve_body( $resp ), true );
		if ( is_array( $data ) ) {
			$state['connected']     = ! empty( $data['connected'] );
			$state['dashboard_url'] = ! empty( $data['dashboard_url'] ) ? $data['dashboard_url'] : $state['dashboard_url'];
		}
		update_option( 'wppseo_connected', $state['connected'] ? 1 : 0 );
		set_transient( 'wppseo_conn_state', $state, 60 );
		return $state;
	}

	private function is_connected() {
		$s = $this->connection_state();
		return (bool) $s['connected'];
	}

	public function menu() {
		add_menu_page(
			__( 'wptaskify', 'wp-pilot-seo' ),
			__( 'wptaskify', 'wp-pilot-seo' ),
			'manage_options',
			'wp-pilot-seo',
			array( $this, 'render' ),
			'dashicons-airplane',
			58
		);

		// Sub-menus (grouped so features merge cleanly, no clutter).
		$subs = array(
			array( __( 'Dashboard', 'wp-pilot-seo' ), 'wp-pilot-seo', array( $this, 'render' ) ),
			array( __( 'AI SEO Score', 'wp-pilot-seo' ), 'wp-pilot-aiseo', array( $this, 'render_aiseo' ) ),
			array( __( 'Connect to AI', 'wp-pilot-seo' ), 'wp-pilot-connect', array( $this, 'render_connect' ) ),
			array( __( 'SEO', 'wp-pilot-seo' ), 'wp-pilot-seo-settings', array( $this, 'render_seo' ) ),
			array( __( 'Studio', 'wp-pilot-seo' ), 'wp-pilot-studio', array( $this, 'render_studio' ) ),
			array( __( 'Activity & Updates', 'wp-pilot-seo' ), 'wp-pilot-activity', array( $this, 'render_activity' ) ),
		);
		foreach ( $subs as $s ) {
			add_submenu_page( 'wp-pilot-seo', $s[0], $s[0], 'manage_options', $s[1], $s[2] );
		}
	}

	public function assets( $hook ) {
		// Load our admin CSS on any wptaskify page (top-level + all sub-pages).
		if ( strpos( (string) $hook, 'wp-pilot' ) === false ) {
			return;
		}
		wp_enqueue_style( 'wppseo-admin', WPPSEO_URL . 'admin.css', array(), WPPSEO_VERSION );
	}

	/** Force an update check, then bounce back. */
	public function handle_check_update() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Not allowed', 'wp-pilot-seo' ) );
		}
		check_admin_referer( 'wppseo_check_update' );
		delete_transient( 'wppseo_update_check' );
		delete_site_transient( 'update_plugins' ); // make WP re-poll
		wp_update_plugins();
		wp_safe_redirect( admin_url( 'admin.php?page=wp-pilot-seo&checked=1' ) );
		exit;
	}

	public function render() {
		$sitemap   = home_url( '/wppseo-sitemap.xml' );
		$connect   = 'https://wptaskify.com/mcp';
		$site_url  = home_url();
		$app_pw    = admin_url( 'profile.php#application-passwords-section' );

		// Update status.
		$update_available = false;
		$new_version      = '';
		$updates = get_site_transient( 'update_plugins' );
		$basename = plugin_basename( WPPSEO_FILE );
		if ( $updates && isset( $updates->response[ $basename ] ) ) {
			$update_available = true;
			$new_version      = $updates->response[ $basename ]->new_version;
		}
		$just_checked = isset( $_GET['checked'] );

		// wptaskify bounced back - DON'T trust the param, re-verify with the server.
		// (A failed connect can still carry ?connected=1; only the server knows.)
		if ( isset( $_GET['connected'] ) || isset( $_GET['disconnected'] ) ) {
			delete_transient( 'wppseo_conn_state' );
		}
		$conn_state  = $this->connection_state();
		$connected   = (bool) $conn_state['connected'];
		$connect_err = isset( $_GET['connect_err'] ) ? sanitize_text_field( wp_unslash( $_GET['connect_err'] ) ) : '';
		?>
		<div class="wrap wppseo-page">
			<h1 style="display:flex;align-items:center;gap:10px">
				<span class="dashicons dashicons-chart-line" style="font-size:30px;width:30px;height:30px;color:#22C55E"></span>
				<?php esc_html_e( 'WP Pilot SEO', 'wp-pilot-seo' ); ?>
				<span style="font-size:13px;color:#646970;font-weight:400">v<?php echo esc_html( WPPSEO_VERSION ); ?></span>
			</h1>

			<div class="wppseo-cards">

				<!-- Onboarding -->
				<div class="wppseo-card">
					<h2><?php esc_html_e( '1. You\'re all set for on-site SEO', 'wp-pilot-seo' ); ?></h2>
					<p><?php esc_html_e( 'Edit any post or page - the "WP Pilot SEO" box appears below the editor. Set a focus keyword, SEO title and meta description, and watch your live SEO score.', 'wp-pilot-seo' ); ?></p>
					<ul class="wppseo-list">
						<li><?php esc_html_e( 'Meta title, description & focus keyword', 'wp-pilot-seo' ); ?></li>
						<li><?php esc_html_e( 'Schema (Article, FAQ, Breadcrumb & more)', 'wp-pilot-seo' ); ?></li>
						<li><?php esc_html_e( 'Open Graph & Twitter cards', 'wp-pilot-seo' ); ?></li>
						<li>
							<?php
							printf(
								/* translators: %s: sitemap URL */
								esc_html__( 'XML sitemap: %s', 'wp-pilot-seo' ),
								'<a href="' . esc_url( $sitemap ) . '" target="_blank" rel="noopener">' . esc_html( $sitemap ) . '</a>'
							);
							?>
						</li>
					</ul>
				</div>

				<!-- Connect to AI (one-click) -->
				<div class="wppseo-card">
					<h2><?php esc_html_e( '2. Connect to AI', 'wp-pilot-seo' ); ?></h2>
					<p><?php esc_html_e( 'Let Claude or ChatGPT write articles, generate images and manage SEO on this site - automatically.', 'wp-pilot-seo' ); ?></p>

					<?php if ( ! $conn_state['reachable'] ) : ?>
						<p class="wppseo-badge update"><?php esc_html_e( 'Could not reach WP Pilot to check the connection. Check your internet / firewall and reload.', 'wp-pilot-seo' ); ?></p>
					<?php endif; ?>

					<?php if ( $connect_err ) : ?>
						<p class="wppseo-badge update"><strong><?php esc_html_e( 'Not connected - reason:', 'wp-pilot-seo' ); ?></strong> <?php
							if ( 'app_passwords_unavailable' === $connect_err ) {
								esc_html_e( 'Application Passwords are disabled on this site. They need HTTPS - enable HTTPS/SSL, then try again.', 'wp-pilot-seo' );
							} elseif ( 'rest_unreachable' === $connect_err ) {
								esc_html_e( 'WP Pilot could not reach this site\'s WordPress REST API (it returned an error). A security plugin, firewall rule, or a PHP/theme error is blocking /wp-json/. Fix that, then Connect again.', 'wp-pilot-seo' );
							} else {
								esc_html_e( 'The connection could not be created. Please try again.', 'wp-pilot-seo' );
							}
						?></p>
						<p><a href="<?php echo esc_url( home_url( '/wp-json/' ) ); ?>" target="_blank" rel="noopener"><?php esc_html_e( 'Test my REST API (should show JSON, not an error)', 'wp-pilot-seo' ); ?> &rarr;</a></p>
					<?php endif; ?>

					<?php if ( $connected ) : ?>
						<p class="wppseo-badge ok"><?php esc_html_e( 'Connected to WP Pilot.', 'wp-pilot-seo' ); ?></p>
						<p>
							<a href="<?php echo esc_url( $conn_state['dashboard_url'] ); ?>" target="_blank" rel="noopener" class="button">
								<?php esc_html_e( 'Open my WP Pilot dashboard', 'wp-pilot-seo' ); ?> &rarr;
							</a>
							<span style="color:#646970;font-size:12px;display:block;margin-top:6px"><?php esc_html_e( 'See this site in your dashboard to confirm it\'s connected.', 'wp-pilot-seo' ); ?></span>
						</p>
						<p style="margin-top:14px"><?php esc_html_e( 'Now add this connector URL in Claude / ChatGPT:', 'wp-pilot-seo' ); ?></p>
						<div class="wppseo-code">
							<code><?php echo esc_html( $connect ); ?></code>
							<button type="button" class="button" onclick="navigator.clipboard.writeText('<?php echo esc_js( $connect ); ?>');this.textContent='<?php echo esc_js( __( 'Copied', 'wp-pilot-seo' ) ); ?>'"><?php esc_html_e( 'Copy', 'wp-pilot-seo' ); ?></button>
						</div>
						<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px">
							<input type="hidden" name="action" value="wppseo_disconnect">
							<?php wp_nonce_field( 'wppseo_disconnect' ); ?>
							<button type="submit" class="button button-link-delete"><?php esc_html_e( 'Disconnect', 'wp-pilot-seo' ); ?></button>
						</form>
					<?php else : ?>
						<p><?php esc_html_e( 'One click sets everything up - we create a secure Application Password for you automatically. No copy-paste.', 'wp-pilot-seo' ); ?></p>
						<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px">
							<input type="hidden" name="action" value="wppseo_connect">
							<?php wp_nonce_field( 'wppseo_connect' ); ?>
							<button type="submit" class="button button-primary button-hero"><?php esc_html_e( 'Connect to WP Pilot', 'wp-pilot-seo' ); ?></button>
						</form>
					<?php endif; ?>
				</div>

				<!-- Updates -->
				<div class="wppseo-card">
					<h2><?php esc_html_e( '3. Updates', 'wp-pilot-seo' ); ?></h2>
					<?php if ( $update_available ) : ?>
						<p class="wppseo-badge update"><?php
							printf( esc_html__( 'Update available: v%s', 'wp-pilot-seo' ), esc_html( $new_version ) );
						?></p>
						<p><a class="button button-primary" href="<?php echo esc_url( admin_url( 'plugins.php' ) ); ?>"><?php esc_html_e( 'Go to Plugins to update', 'wp-pilot-seo' ); ?></a></p>
					<?php else : ?>
						<p class="wppseo-badge ok"><?php
							echo $just_checked
								? esc_html__( 'You\'re on the latest version.', 'wp-pilot-seo' )
								: esc_html__( 'Updates install automatically when available.', 'wp-pilot-seo' );
						?></p>
					<?php endif; ?>
					<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:10px">
						<input type="hidden" name="action" value="wppseo_check_update">
						<?php wp_nonce_field( 'wppseo_check_update' ); ?>
						<button type="submit" class="button"><?php esc_html_e( 'Check for updates now', 'wp-pilot-seo' ); ?></button>
					</form>
				</div>

			</div>
		</div>

		<style>
			.wppseo-page .wppseo-cards{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));max-width:1100px;margin-top:20px}
			.wppseo-page .wppseo-card{background:#fff;border:1px solid #dcdcde;border-radius:8px;padding:22px}
			.wppseo-page .wppseo-card h2{margin-top:0;font-size:17px}
			.wppseo-page .wppseo-list,.wppseo-page .wppseo-steps{margin:14px 0;padding-left:20px}
			.wppseo-page .wppseo-list li,.wppseo-page .wppseo-steps li{margin:7px 0}
			.wppseo-page .wppseo-code{display:flex;gap:8px;align-items:center;background:#f6f7f7;border:1px solid #dcdcde;border-radius:6px;padding:8px 10px;margin-top:10px}
			.wppseo-page .wppseo-code code{flex:1;word-break:break-all;background:none;font-size:12px}
			.wppseo-page .wppseo-badge{display:inline-block;padding:6px 12px;border-radius:999px;font-weight:600;font-size:13px}
			.wppseo-page .wppseo-badge.ok{background:#edfaef;color:#00a32a}
			.wppseo-page .wppseo-badge.update{background:#fcf3e6;color:#bd7b00}
		</style>
		<?php
	}

	/** Shared page wrapper (title + version) for sub-pages. */
	private function page_open( $title ) {
		echo '<div class="wrap wppseo-page"><h1 style="display:flex;align-items:center;gap:10px">';
		echo '<span class="dashicons dashicons-airplane" style="font-size:28px;width:28px;height:28px;color:#2563eb"></span>';
		echo esc_html( $title );
		echo ' <span style="font-size:13px;color:#646970;font-weight:400">v' . esc_html( WPPSEO_VERSION ) . '</span></h1>';
	}
	private function page_close() {
		echo '</div>';
	}

	// ---- Sub-page: AI SEO Score (5 rings, computed here) ----------------
	public function render_aiseo() {
		$data = WPPSEO_AiSeo::score( 50 );
		$rep  = WPPSEO_AiSeo::report();
		$cats = $data['categories'];
		$iss  = $data['issues'];
		$names = array(
			'on_page' => __( 'On-Page', 'wp-pilot-seo' ),
			'technical' => __( 'Technical', 'wp-pilot-seo' ),
			'aeo' => __( 'AEO', 'wp-pilot-seo' ),
			'geo' => __( 'GEO', 'wp-pilot-seo' ),
			'authority_eeat' => __( 'Authority', 'wp-pilot-seo' ),
		);
		$color = function( $v ) {
			return $v >= 75 ? '#22C55E' : ( $v >= 50 ? '#E5A50A' : '#E0533D' );
		};
		$ring = function( $label, $v ) use ( $color ) {
			$r = 30; $c = 2 * M_PI * $r; $off = $c * ( 1 - $v / 100 ); $col = $color( $v );
			return '<div style="text-align:center">'
				. '<svg width=76 height=76 viewBox="0 0 76 76" style="transform:rotate(-90deg)">'
				. '<circle cx=38 cy=38 r=' . $r . ' fill=none stroke="#e2e4e7" stroke-width=7/>'
				. '<circle cx=38 cy=38 r=' . $r . ' fill=none stroke="' . $col . '" stroke-width=7 stroke-linecap=round '
				. 'stroke-dasharray="' . $c . '" stroke-dashoffset="' . $off . '"/></svg>'
				. '<div style="font-weight:700;font-size:1.05rem;color:' . $col . ';margin-top:-6px">' . intval( $v ) . '</div>'
				. '<div style="font-size:.8rem;color:#646970">' . esc_html( $label ) . '</div></div>';
		};
		$this->page_open( __( 'AI SEO Score', 'wp-pilot-seo' ) );
		?>
		<div class="wppseo-card">
			<p><?php esc_html_e( 'Your site\'s modern, AI-era SEO across 5 dimensions - measured from your published content. Ask your AI assistant to fix any weak area.', 'wp-pilot-seo' ); ?></p>
			<div style="display:flex;gap:28px;align-items:center;flex-wrap:wrap;margin-top:12px">
				<div style="text-align:center;min-width:150px">
					<div style="font-size:3rem;font-weight:800;line-height:1;color:<?php echo esc_attr( $color( $data['overall'] ) ); ?>"><?php echo intval( $data['overall'] ); ?></div>
					<div style="color:#646970;font-size:.85rem;margin-top:4px"><?php esc_html_e( 'AI SEO Score', 'wp-pilot-seo' ); ?></div>
					<?php if ( ! empty( $rep['before']['overall'] ) ) :
						$d = $data['overall'] - intval( $rep['before']['overall'] ); ?>
						<div style="font-size:.85rem;font-weight:700;margin-top:4px;color:<?php echo $d >= 0 ? '#22C55E' : '#E0533D'; ?>">
							<?php echo $d >= 0 ? '▲ ' . $d : '▼ ' . abs( $d ); ?> <?php esc_html_e( 'vs last week', 'wp-pilot-seo' ); ?>
						</div>
					<?php endif; ?>
				</div>
				<div style="display:flex;gap:22px;flex-wrap:wrap;flex:1">
					<?php foreach ( $names as $k => $lbl ) { echo $ring( $lbl, isset( $cats[ $k ] ) ? $cats[ $k ] : 0 ); } ?>
				</div>
			</div>
		</div>

		<div class="wppseo-card" style="margin-top:14px">
			<h2><?php esc_html_e( 'Issues to fix', 'wp-pilot-seo' ); ?></h2>
			<?php
			$chips = array(
				array( $iss['missing_meta_description'], __( 'posts missing meta description', 'wp-pilot-seo' ) ),
				array( $iss['images_missing_alt'], __( 'images missing alt text', 'wp-pilot-seo' ) ),
				array( $iss['posts_without_schema'], __( 'posts without schema', 'wp-pilot-seo' ) ),
				array( $iss['orphan_pages'], __( 'orphan pages', 'wp-pilot-seo' ) ),
				array( $iss['thin_posts'], __( 'thin posts', 'wp-pilot-seo' ) ),
			);
			$any = false;
			echo '<div style="display:flex;flex-wrap:wrap;gap:10px">';
			foreach ( $chips as $c ) {
				if ( $c[0] > 0 ) {
					$any = true;
					echo '<span class="wppseo-badge update"><strong>' . intval( $c[0] ) . '</strong> ' . esc_html( $c[1] ) . '</span>';
				}
			}
			echo '</div>';
			if ( ! $any ) {
				echo '<p class="wppseo-badge ok">' . esc_html__( 'No major issues found. Nice.', 'wp-pilot-seo' ) . '</p>';
			}
			?>
			<p style="margin-top:14px;color:#646970"><?php echo esc_html( sprintf( __( 'Scored %d published posts. Tell your AI assistant "fix my AI SEO" to improve these.', 'wp-pilot-seo' ), $data['posts_scored'] ) ); ?></p>
		</div>
		<?php
		$this->page_close();
	}

	// ---- Sub-page: Connect to AI ----------------------------------------
	public function render_connect() {
		$connect = 'https://wptaskify.com/mcp';
		$state   = $this->connection_state();
		$this->page_open( __( 'Connect to AI', 'wp-pilot-seo' ) );
		?>
		<div class="wppseo-card">
			<p><?php esc_html_e( 'Connect this site to Claude or ChatGPT so the AI can write, design, optimize SEO, and manage your site.', 'wp-pilot-seo' ); ?></p>
			<?php if ( $state['connected'] ) : ?>
				<p class="wppseo-badge ok"><?php esc_html_e( 'Connected to WP Pilot.', 'wp-pilot-seo' ); ?></p>
				<p><a class="button" target="_blank" rel="noopener" href="<?php echo esc_url( $state['dashboard_url'] ); ?>"><?php esc_html_e( 'Open my WP Pilot dashboard', 'wp-pilot-seo' ); ?> &rarr;</a></p>
				<p style="margin-top:12px"><?php esc_html_e( 'Connector URL for Claude / ChatGPT:', 'wp-pilot-seo' ); ?></p>
				<div class="wppseo-code"><code><?php echo esc_html( $connect ); ?></code>
					<button type="button" class="button" onclick="navigator.clipboard.writeText('<?php echo esc_js( $connect ); ?>');this.textContent='<?php echo esc_js( __( 'Copied', 'wp-pilot-seo' ) ); ?>'"><?php esc_html_e( 'Copy', 'wp-pilot-seo' ); ?></button>
				</div>
				<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px">
					<input type="hidden" name="action" value="wppseo_disconnect">
					<?php wp_nonce_field( 'wppseo_disconnect' ); ?>
					<button type="submit" class="button button-link-delete"><?php esc_html_e( 'Disconnect', 'wp-pilot-seo' ); ?></button>
				</form>
			<?php else : ?>
				<p><?php esc_html_e( 'One click sets everything up - we create a secure Application Password for you automatically.', 'wp-pilot-seo' ); ?></p>
				<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px">
					<input type="hidden" name="action" value="wppseo_connect">
					<?php wp_nonce_field( 'wppseo_connect' ); ?>
					<button type="submit" class="button button-primary button-hero"><?php esc_html_e( 'Connect to WP Pilot', 'wp-pilot-seo' ); ?></button>
				</form>
			<?php endif; ?>
		</div>
		<?php
		$this->page_close();
	}

	// ---- Sub-page: SEO ---------------------------------------------------
	public function render_seo() {
		$sitemap = home_url( '/wppseo-sitemap.xml' );
		$this->page_open( __( 'SEO', 'wp-pilot-seo' ) );
		?>
		<div class="wppseo-card">
			<h2><?php esc_html_e( 'How SEO works here', 'wp-pilot-seo' ); ?></h2>
			<p><?php esc_html_e( 'Edit each post/page SEO in the "WP Pilot SEO" box under the editor - meta title, description, focus keyword, social preview and schema. Your AI assistant can also set all of these automatically.', 'wp-pilot-seo' ); ?></p>
			<ul style="list-style:disc;padding-left:20px">
				<li><?php esc_html_e( 'Meta titles & descriptions, focus keyword, Open Graph & Twitter cards', 'wp-pilot-seo' ); ?></li>
				<li><?php esc_html_e( 'Structured data (schema) for rich results', 'wp-pilot-seo' ); ?></li>
				<li><?php esc_html_e( 'Live SEO score on every post', 'wp-pilot-seo' ); ?></li>
			</ul>
			<p><strong><?php esc_html_e( 'XML sitemap:', 'wp-pilot-seo' ); ?></strong>
				<a href="<?php echo esc_url( $sitemap ); ?>" target="_blank" rel="noopener"><?php echo esc_html( $sitemap ); ?></a></p>
		</div>
		<?php
		$this->page_close();
	}

	// ---- Sub-page: Studio (custom CSS + backups) ------------------------
	public function render_studio() {
		$css_len = strlen( (string) get_option( 'wpps_custom_css', '' ) );
		$backups = $this->list_backups();
		$this->page_open( __( 'Studio', 'wp-pilot-seo' ) );
		?>
		<div class="wppseo-card">
			<h2><?php esc_html_e( 'AI build tools', 'wp-pilot-seo' ); ?></h2>
			<p><?php esc_html_e( 'Your AI assistant can restyle the whole site with custom CSS and safely create or edit themes and plugins. Every file change is backed up first, and PHP is syntax-checked before saving - so a bad edit can never take your site down.', 'wp-pilot-seo' ); ?></p>
			<p><strong><?php esc_html_e( 'Custom CSS:', 'wp-pilot-seo' ); ?></strong>
				<?php echo $css_len ? esc_html( sprintf( '%d bytes active', $css_len ) ) : esc_html__( 'none yet', 'wp-pilot-seo' ); ?></p>
			<p class="wppseo-badge update" style="margin-top:6px"><?php esc_html_e( 'Editing existing theme/plugin files (like functions.php) is powerful but risky - the AI will warn you and ask before doing it, and always keeps a backup.', 'wp-pilot-seo' ); ?></p>
		</div>
		<div class="wppseo-card" style="margin-top:14px">
			<h2><?php esc_html_e( 'Automatic backups', 'wp-pilot-seo' ); ?>
				<span style="font-size:13px;color:#646970;font-weight:400">(<?php echo count( $backups ); ?>)</span></h2>
			<?php if ( $backups ) : ?>
				<ul style="font-family:monospace;font-size:12px;max-height:260px;overflow:auto">
					<?php foreach ( array_slice( $backups, 0, 40 ) as $b ) : ?>
						<li><?php echo esc_html( $b ); ?></li>
					<?php endforeach; ?>
				</ul>
				<p style="color:#646970;font-size:12px"><?php echo esc_html( sprintf( __( 'Stored in %s', 'wp-pilot-seo' ), WPPSEO_BACKUP_DIR ) ); ?></p>
			<?php else : ?>
				<p><?php esc_html_e( 'No file edits yet - backups will appear here the moment the AI touches a file.', 'wp-pilot-seo' ); ?></p>
			<?php endif; ?>
		</div>
		<?php
		$this->page_close();
	}

	private function list_backups() {
		$out = array();
		if ( defined( 'WPPSEO_BACKUP_DIR' ) && is_dir( WPPSEO_BACKUP_DIR ) ) {
			foreach ( scandir( WPPSEO_BACKUP_DIR ) as $f ) {
				if ( in_array( $f, array( '.', '..', '.htaccess', 'index.php' ), true ) ) {
					continue;
				}
				$out[] = $f;
			}
			rsort( $out );
		}
		return $out;
	}

	// ---- Sub-page: Activity & Updates -----------------------------------
	public function render_activity() {
		$update_available = false;
		$new_version      = '';
		$updates  = get_site_transient( 'update_plugins' );
		$basename = plugin_basename( WPPSEO_FILE );
		if ( $updates && isset( $updates->response[ $basename ] ) ) {
			$update_available = true;
			$new_version      = $updates->response[ $basename ]->new_version;
		}
		$this->page_open( __( 'Activity & Updates', 'wp-pilot-seo' ) );
		?>
		<div class="wppseo-card">
			<h2><?php esc_html_e( 'Updates', 'wp-pilot-seo' ); ?></h2>
			<?php if ( $update_available ) : ?>
				<p class="wppseo-badge update"><?php printf( esc_html__( 'Update available: v%s', 'wp-pilot-seo' ), esc_html( $new_version ) ); ?></p>
				<p><a class="button button-primary" href="<?php echo esc_url( admin_url( 'plugins.php' ) ); ?>"><?php esc_html_e( 'Go to Plugins to update', 'wp-pilot-seo' ); ?></a></p>
			<?php else : ?>
				<p class="wppseo-badge ok"><?php echo isset( $_GET['checked'] ) ? esc_html__( 'You are on the latest version.', 'wp-pilot-seo' ) : esc_html__( 'Updates install automatically when available.', 'wp-pilot-seo' ); ?></p>
			<?php endif; ?>
			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:10px">
				<input type="hidden" name="action" value="wppseo_check_update">
				<?php wp_nonce_field( 'wppseo_check_update' ); ?>
				<button type="submit" class="button"><?php esc_html_e( 'Check for updates now', 'wp-pilot-seo' ); ?></button>
			</form>
		</div>
		<div class="wppseo-card" style="margin-top:14px">
			<h2><?php esc_html_e( 'Recent AI activity', 'wp-pilot-seo' ); ?></h2>
			<?php
			$log = get_option( 'wppseo_activity_log', array() );
			if ( is_array( $log ) && $log ) :
				?>
				<ul style="font-size:13px;max-height:300px;overflow:auto">
					<?php foreach ( array_slice( array_reverse( $log ), 0, 50 ) as $row ) : ?>
						<li><span style="color:#646970"><?php echo esc_html( isset( $row['time'] ) ? $row['time'] : '' ); ?></span> - <?php echo esc_html( isset( $row['msg'] ) ? $row['msg'] : '' ); ?></li>
					<?php endforeach; ?>
				</ul>
			<?php else : ?>
				<p><?php esc_html_e( 'No AI activity recorded yet. Actions the assistant takes on your site will be listed here.', 'wp-pilot-seo' ); ?></p>
			<?php endif; ?>
		</div>
		<?php
		$this->page_close();
	}
}
