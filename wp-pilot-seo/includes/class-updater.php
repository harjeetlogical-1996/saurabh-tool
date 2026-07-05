<?php
/**
 * Self-hosted auto-updater. Polls the wptaskify server for a newer version and
 * surfaces it in WordPress' normal "Update available" / one-click update flow.
 *
 * Server must expose:
 *   GET {UPDATE_URL}  -> JSON: {version, download_url, requires, tested, requires_php}
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Updater {

	private static $instance = null;
	private $slug;        // wp-pilot-seo
	private $basename;    // wp-pilot-seo/wp-pilot-seo.php
	private $update_url;
	private $cache_key = 'wppseo_update_check';

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		$this->basename   = plugin_basename( WPPSEO_FILE );
		$this->slug       = dirname( $this->basename );
		// The wptaskify server that hosts version info + the zip.
		$this->update_url = 'https://wptaskify.com/plugin/update.json';

		add_filter( 'pre_set_site_transient_update_plugins', array( $this, 'check' ) );
		add_filter( 'plugins_api', array( $this, 'info' ), 20, 3 );
		add_action( 'upgrader_process_complete', array( $this, 'clear_cache' ), 10, 0 );
		// Enable background auto-updates for THIS plugin, so users don't have to
		// click "update" - WordPress installs new versions automatically.
		add_filter( 'auto_update_plugin', array( $this, 'auto_update' ), 10, 2 );
	}

	/** Auto-update our own plugin (leave every other plugin's setting untouched). */
	public function auto_update( $update, $item ) {
		if ( isset( $item->plugin ) && $item->plugin === $this->basename ) {
			return true;
		}
		return $update;
	}

	/** Fetch + cache remote version info (6h). */
	private function remote() {
		$cached = get_transient( $this->cache_key );
		if ( false !== $cached ) {
			return $cached;
		}
		$res = wp_remote_get( $this->update_url, array( 'timeout' => 10 ) );
		if ( is_wp_error( $res ) || 200 !== wp_remote_retrieve_response_code( $res ) ) {
			set_transient( $this->cache_key, array(), HOUR_IN_SECONDS );
			return array();
		}
		$data = json_decode( wp_remote_retrieve_body( $res ), true );
		if ( ! is_array( $data ) ) {
			$data = array();
		}
		set_transient( $this->cache_key, $data, HOUR_IN_SECONDS );
		return $data;
	}

	/** Inject our update into the plugins update transient. */
	public function check( $transient ) {
		if ( empty( $transient->checked ) ) {
			return $transient;
		}
		$remote = $this->remote();
		if ( empty( $remote['version'] ) || empty( $remote['download_url'] ) ) {
			return $transient;
		}
		if ( version_compare( WPPSEO_VERSION, $remote['version'], '<' ) ) {
			$obj = (object) array(
				'slug'        => $this->slug,
				'plugin'      => $this->basename,
				'new_version' => $remote['version'],
				'package'     => $remote['download_url'],
				'url'         => 'https://wptaskify.com',
				'tested'      => isset( $remote['tested'] ) ? $remote['tested'] : '',
				'requires'    => isset( $remote['requires'] ) ? $remote['requires'] : '',
				'requires_php'=> isset( $remote['requires_php'] ) ? $remote['requires_php'] : '',
			);
			$transient->response[ $this->basename ] = $obj;
		}
		return $transient;
	}

	/** "View details" popup. */
	public function info( $result, $action, $args ) {
		if ( 'plugin_information' !== $action || empty( $args->slug ) || $args->slug !== $this->slug ) {
			return $result;
		}
		$remote = $this->remote();
		if ( empty( $remote['version'] ) ) {
			return $result;
		}
		return (object) array(
			'name'          => 'wptaskify',
			'slug'          => $this->slug,
			'version'       => $remote['version'],
			'requires'      => isset( $remote['requires'] ) ? $remote['requires'] : '5.6',
			'requires_php'  => isset( $remote['requires_php'] ) ? $remote['requires_php'] : '7.4',
			'tested'        => isset( $remote['tested'] ) ? $remote['tested'] : '',
			'download_link' => $remote['download_url'],
			'sections'      => array(
				'description' => isset( $remote['description'] ) ? $remote['description'] : 'Free, full-featured SEO for WordPress.',
				'changelog'   => isset( $remote['changelog'] ) ? $remote['changelog'] : '',
			),
		);
	}

	public function clear_cache() {
		delete_transient( $this->cache_key );
	}
}
