<?php
/**
 * Admin screen — Fetch Now button, last-run status, and log.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'admin_menu', function () {
	add_menu_page(
		'FII Flows',
		'FII Flows',
		'manage_options',
		'fii-flows',
		'fiif_admin_page',
		'dashicons-chart-line',
		58
	);
} );

function fiif_admin_page() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	// Handle "Fetch Now".
	if ( isset( $_POST['fiif_fetch_now'] ) && check_admin_referer( 'fiif_fetch_now_action', 'fiif_nonce' ) ) {
		$res = fiif_fetch_all();
		echo '<div class="notice notice-success"><p>Fetch complete: '
			. 'flows = ' . ( $res['flows'] ? 'OK' : 'FAILED' ) . ', '
			. 'movers = ' . ( $res['movers'] ? 'OK' : 'FAILED' ) . '.</p></div>';
	}

	// Handle "Clear NSE cookie cache".
	if ( isset( $_POST['fiif_clear_cookies'] ) && check_admin_referer( 'fiif_fetch_now_action', 'fiif_nonce' ) ) {
		delete_transient( 'fiif_nse_cookies' );
		echo '<div class="notice notice-info"><p>NSE cookie cache cleared.</p></div>';
	}

	$last_run = get_option( 'fiif_last_run', 'never' );
	$next     = wp_next_scheduled( 'fiif_daily_fetch' );
	$log      = get_option( 'fiif_log', array() );
	$flow     = fiif_get_latest_flow();
	?>
	<div class="wrap">
		<h1>FII Flows — Control Panel</h1>

		<h2>Status</h2>
		<table class="widefat striped" style="max-width:680px">
			<tr><td><strong>Last fetch run</strong></td><td><?php echo esc_html( $last_run ); ?></td></tr>
			<tr><td><strong>Next scheduled fetch</strong></td>
				<td><?php echo $next ? esc_html( mysql2date( 'd M Y, g:i a', gmdate( 'Y-m-d H:i:s', $next ) ) ) : 'not scheduled'; ?></td></tr>
			<tr><td><strong>Latest data date</strong></td>
				<td><?php echo $flow ? esc_html( $flow->trade_date ) : '— (no data yet)'; ?></td></tr>
		</table>

		<h2 style="margin-top:24px">Actions</h2>
		<form method="post">
			<?php wp_nonce_field( 'fiif_fetch_now_action', 'fiif_nonce' ); ?>
			<button type="submit" name="fiif_fetch_now" class="button button-primary">Fetch Now</button>
			<button type="submit" name="fiif_clear_cookies" class="button">Clear NSE Cookie Cache</button>
		</form>

		<h2 style="margin-top:24px">How to use the shortcodes</h2>
		<p>Create WordPress pages and paste these:</p>
		<ul style="list-style:disc;margin-left:20px">
			<li><code>[fii_dii_table days="30"]</code> — FII/DII daily flows table</li>
			<li><code>[fii_dii_chart days="30"]</code> — net flow trend chart</li>
			<li><code>[fii_fno]</code> — FII F&amp;O positions</li>
			<li><code>[fii_mood]</code> — Bullish/Bearish mood meter</li>
			<li><code>[top_gainers limit="10"]</code> / <code>[top_losers]</code> / <code>[most_active]</code></li>
			<li><code>[stocks_directory]</code> — searchable stock directory</li>
		</ul>

		<h2 style="margin-top:24px">Log (latest 50)</h2>
		<textarea readonly style="width:100%;height:240px;font-family:monospace;font-size:12px"><?php
			echo esc_textarea( implode( "\n", (array) $log ) );
		?></textarea>
	</div>
	<?php
}
