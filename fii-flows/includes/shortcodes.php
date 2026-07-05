<?php
/**
 * Shortcodes — the front-end output.
 *
 * Available:
 *   [fii_dii_table days="30"]   FII/DII daily flows table + AI-answer block + last-updated
 *   [fii_dii_chart days="30"]   Net flow trend chart (Chart.js)
 *   [fii_fno]                   FII F&O positions + long/short ratio
 *   [fii_mood]                  Bullish/Bearish mood meter
 *   [top_gainers limit="10"]    Top gaining stocks today
 *   [top_losers limit="10"]     Top losing stocks today
 *   [most_active limit="10"]    Most active by traded value
 *   [stocks_directory]          Searchable/filterable stock directory
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Format a ₹ crore number with sign + color class. */
function fiif_fmt_cr( $n ) {
	$n   = (float) $n;
	$cls = $n > 0 ? 'fiif-pos' : ( $n < 0 ? 'fiif-neg' : '' );
	$txt = number_format( abs( $n ), 2 );
	$sgn = $n > 0 ? '+' : ( $n < 0 ? '-' : '' );
	return '<span class="' . $cls . '">' . $sgn . '₹' . $txt . ' Cr</span>';
}

function fiif_last_updated_line( $row ) {
	if ( ! $row || empty( $row->updated_at ) ) {
		return '';
	}
	$ts = mysql2date( 'd M Y, g:i a', $row->updated_at );
	return '<p class="fiif-updated">Last updated: ' . esc_html( $ts ) . ' IST · Source: NSE (end-of-day)</p>';
}

/* ---------------- FII/DII TABLE ---------------- */
add_shortcode( 'fii_dii_table', function ( $atts ) {
	$a    = shortcode_atts( array( 'days' => 30 ), $atts );
	$rows = fiif_get_flows( absint( $a['days'] ) );
	if ( ! $rows ) {
		return '<div class="fiif-empty">FII/DII data not fetched yet. Run “Fetch Now” in the admin.</div>';
	}
	$latest = $rows[0];

	// AI-answer block (first thing on the page — gets cited by AI engines).
	$verdict = $latest->fii_net >= 0 ? 'net buyers' : 'net sellers';
	$dverdict = $latest->dii_net >= 0 ? 'net buyers' : 'net sellers';
	ob_start(); ?>
	<div class="fiif-answer">
		<p><strong>On <?php echo esc_html( mysql2date( 'd M Y', $latest->trade_date ) ); ?>, FIIs were <?php echo esc_html( $verdict ); ?></strong>
		with a net of <?php echo fiif_fmt_cr( $latest->fii_net ); ?>, while DIIs were <?php echo esc_html( $dverdict ); ?>
		at <?php echo fiif_fmt_cr( $latest->dii_net ); ?>. Net flow = gross buy − gross sell; positive net is bullish, negative is caution.</p>
	</div>

	<table class="fiif-table">
		<thead><tr>
			<th>Date</th>
			<th>FII Buy</th><th>FII Sell</th><th>FII Net</th>
			<th>DII Buy</th><th>DII Sell</th><th>DII Net</th>
		</tr></thead>
		<tbody>
		<?php foreach ( $rows as $r ) : ?>
			<tr>
				<td><?php echo esc_html( mysql2date( 'd M Y', $r->trade_date ) ); ?></td>
				<td><?php echo number_format( $r->fii_buy, 2 ); ?></td>
				<td><?php echo number_format( $r->fii_sell, 2 ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->fii_net ); ?></td>
				<td><?php echo number_format( $r->dii_buy, 2 ); ?></td>
				<td><?php echo number_format( $r->dii_sell, 2 ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->dii_net ); ?></td>
			</tr>
		<?php endforeach; ?>
		</tbody>
	</table>
	<?php echo fiif_last_updated_line( $latest );
	return ob_get_clean();
} );

/* ---------------- FII/DII CHART ---------------- */
add_shortcode( 'fii_dii_chart', function ( $atts ) {
	$a    = shortcode_atts( array( 'days' => 30 ), $atts );
	$rows = array_reverse( fiif_get_flows( absint( $a['days'] ) ) ); // oldest -> newest
	if ( ! $rows ) {
		return '';
	}
	$labels = array();
	$fii    = array();
	$dii    = array();
	foreach ( $rows as $r ) {
		$labels[] = mysql2date( 'd M', $r->trade_date );
		$fii[]    = (float) $r->fii_net;
		$dii[]    = (float) $r->dii_net;
	}
	$data = wp_json_encode( array(
		'labels' => $labels,
		'fii'    => $fii,
		'dii'    => $dii,
	) );
	return '<div class="fiif-chart-wrap"><canvas class="fiif-chart" data-fiif-chart=\'' . esc_attr( $data ) . '\'></canvas></div>';
} );

/* ---------------- FII F&O ---------------- */
add_shortcode( 'fii_fno', function () {
	$r = fiif_get_latest_fno();
	if ( ! $r ) {
		return '<div class="fiif-empty">FII F&O data not available yet.</div>';
	}
	$ratio = (float) $r->long_short_ratio;
	$bias  = $ratio > 1 ? 'bullish' : ( $ratio < 1 && $ratio > 0 ? 'bearish' : 'neutral' );
	ob_start(); ?>
	<div class="fiif-answer">
		<p><strong>FIIs are positioned <?php echo esc_html( $bias ); ?> in F&O</strong> with a long/short ratio of
		<?php echo esc_html( number_format( $ratio, 2 ) ); ?> as of <?php echo esc_html( mysql2date( 'd M Y', $r->trade_date ) ); ?>.
		A ratio above 1 means more longs (bullish); below 1 means more shorts (bearish).</p>
	</div>
	<table class="fiif-table">
		<tr><th>Index Futures Long</th><td><?php echo number_format( $r->idx_fut_long ); ?></td>
			<th>Index Futures Short</th><td><?php echo number_format( $r->idx_fut_short ); ?></td></tr>
		<tr><th>Stock Futures Long</th><td><?php echo number_format( $r->stock_fut_long ); ?></td>
			<th>Stock Futures Short</th><td><?php echo number_format( $r->stock_fut_short ); ?></td></tr>
		<tr><th>Index Call Long</th><td><?php echo number_format( $r->idx_call_long ); ?></td>
			<th>Index Put Long</th><td><?php echo number_format( $r->idx_put_long ); ?></td></tr>
	</table>
	<?php echo fiif_last_updated_line( $r );
	return ob_get_clean();
} );

/* ---------------- MOOD METER ---------------- */
add_shortcode( 'fii_mood', function () {
	$flow = fiif_get_latest_flow();
	$fno  = fiif_get_latest_fno();
	if ( ! $flow && ! $fno ) {
		return '<div class="fiif-empty">Not enough data for mood yet.</div>';
	}
	// Simple score: cash net direction + F&O ratio.
	$score = 0;
	if ( $flow ) {
		$score += $flow->fii_net > 0 ? 1 : -1;
	}
	if ( $fno && $fno->long_short_ratio > 0 ) {
		$score += $fno->long_short_ratio > 1 ? 1 : -1;
	}
	if ( $score >= 1 ) { $mood = 'Bullish'; $cls = 'fiif-pos'; }
	elseif ( $score <= -1 ) { $mood = 'Bearish'; $cls = 'fiif-neg'; }
	else { $mood = 'Neutral'; $cls = ''; }

	return '<div class="fiif-mood ' . $cls . '"><span class="fiif-mood-label">FII Mood Today</span>'
		. '<span class="fiif-mood-value">' . esc_html( $mood ) . '</span></div>';
} );

/* ---------------- MOVERS (gainers / losers / active) ---------------- */
function fiif_render_movers( $dir, $limit, $heading ) {
	$rows = fiif_get_movers( $dir, absint( $limit ) );
	if ( ! $rows ) {
		return '<div class="fiif-empty">No ' . esc_html( $heading ) . ' data yet.</div>';
	}
	ob_start(); ?>
	<table class="fiif-table fiif-movers">
		<thead><tr><th>#</th><th>Stock</th><th>LTP (₹)</th><th>Change %</th></tr></thead>
		<tbody>
		<?php $i = 1; foreach ( $rows as $r ) :
			$cls  = $r->pct_change >= 0 ? 'fiif-pos' : 'fiif-neg';
			$slug = strtolower( $r->symbol ); ?>
			<tr>
				<td><?php echo $i++; ?></td>
				<td><a href="<?php echo esc_url( home_url( '/stocks/' . $slug . '/' ) ); ?>"><?php echo esc_html( $r->symbol ); ?></a></td>
				<td><?php echo number_format( $r->ltp, 2 ); ?></td>
				<td class="<?php echo $cls; ?>"><?php echo ( $r->pct_change >= 0 ? '+' : '' ) . number_format( $r->pct_change, 2 ); ?>%</td>
			</tr>
		<?php endforeach; ?>
		</tbody>
	</table>
	<?php
	return ob_get_clean();
}
add_shortcode( 'top_gainers', function ( $atts ) {
	$a = shortcode_atts( array( 'limit' => 10 ), $atts );
	return fiif_render_movers( 'gainers', $a['limit'], 'gainers' );
} );
add_shortcode( 'top_losers', function ( $atts ) {
	$a = shortcode_atts( array( 'limit' => 10 ), $atts );
	return fiif_render_movers( 'losers', $a['limit'], 'losers' );
} );
add_shortcode( 'most_active', function ( $atts ) {
	$a = shortcode_atts( array( 'limit' => 10 ), $atts );
	return fiif_render_movers( 'active', $a['limit'], 'most active' );
} );

/* ---------------- FII STATS STRIP ---------------- */
add_shortcode( 'fii_stats', function () {
	$t30 = fiif_period_totals( 30 );
	$t7  = fiif_period_totals( 7 );
	$streak = fiif_streak( 'fii' );
	$ext = fiif_extremes();
	ob_start(); ?>
	<div class="fiif-stats-grid">
		<div class="fiif-stat-box">
			<span class="fiif-sb-label">FII Net · Last 7 days</span>
			<span class="fiif-sb-value <?php echo $t7->fii >= 0 ? 'fiif-pos' : 'fiif-neg'; ?>"><?php echo fiif_fmt_cr( $t7->fii ); ?></span>
		</div>
		<div class="fiif-stat-box">
			<span class="fiif-sb-label">FII Net · Last 30 days</span>
			<span class="fiif-sb-value <?php echo $t30->fii >= 0 ? 'fiif-pos' : 'fiif-neg'; ?>"><?php echo fiif_fmt_cr( $t30->fii ); ?></span>
		</div>
		<div class="fiif-stat-box">
			<span class="fiif-sb-label">Current FII Streak</span>
			<span class="fiif-sb-value <?php echo $streak['dir'] === 'buying' ? 'fiif-pos' : ( $streak['dir'] === 'selling' ? 'fiif-neg' : '' ); ?>">
				<?php echo $streak['days'] > 0 ? esc_html( $streak['days'] . ' days ' . $streak['dir'] ) : '—'; ?>
			</span>
		</div>
		<?php if ( $ext['max_buy'] ) : ?>
		<div class="fiif-stat-box">
			<span class="fiif-sb-label">Biggest Buy Day</span>
			<span class="fiif-sb-value fiif-pos"><?php echo fiif_fmt_cr( $ext['max_buy']->fii_net ); ?></span>
			<span class="fiif-sb-sub"><?php echo esc_html( mysql2date( 'd M Y', $ext['max_buy']->trade_date ) ); ?></span>
		</div>
		<?php endif; ?>
	</div>
	<?php
	return ob_get_clean();
} );

/* ---------------- FII STREAK (text badge) ---------------- */
add_shortcode( 'fii_streak', function () {
	$s = fiif_streak( 'fii' );
	if ( $s['days'] < 1 ) {
		return '<div class="fiif-empty">No clear streak right now.</div>';
	}
	$cls = $s['dir'] === 'buying' ? 'fiif-pos' : 'fiif-neg';
	$up = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline></svg>';
	$down = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"></polyline><polyline points="16 17 22 17 22 11"></polyline></svg>';
	$icon = $s['dir'] === 'buying' ? $up : $down;
	return '<div class="fiif-streak ' . $cls . '"><span class="fiif-streak-ico">' . $icon . '</span><span>FIIs have been <strong>' . esc_html( $s['dir'] )
		. '</strong> for <strong>' . esc_html( $s['days'] ) . ' straight trading day' . ( $s['days'] > 1 ? 's' : '' ) . '</strong>.</span></div>';
} );

/* ---------------- MONTHLY TOTALS ---------------- */
add_shortcode( 'fii_monthly', function ( $atts ) {
	$a    = shortcode_atts( array( 'months' => 6 ), $atts );
	$rows = fiif_monthly_totals( absint( $a['months'] ) );
	if ( ! $rows ) {
		return '<div class="fiif-empty">No monthly data yet.</div>';
	}
	ob_start(); ?>
	<table class="fiif-table">
		<thead><tr><th>Month</th><th>FII Net</th><th>DII Net</th><th>Trading Days</th></tr></thead>
		<tbody>
		<?php foreach ( $rows as $r ) : ?>
			<tr>
				<td><?php echo esc_html( date( 'M Y', strtotime( $r->ym . '-01' ) ) ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->fii_net ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->dii_net ); ?></td>
				<td><?php echo esc_html( $r->days ); ?></td>
			</tr>
		<?php endforeach; ?>
		</tbody>
	</table>
	<?php
	return ob_get_clean();
} );

/* ---------------- SECTOR FLOWS ---------------- */
add_shortcode( 'fii_sectors', function ( $atts ) {
	$a    = shortcode_atts( array( 'order' => 'fortnight', 'limit' => 0 ), $atts );
	$rows = fiif_get_sector_flows( $a['order'] );
	if ( ! $rows ) {
		return '<div class="fiif-empty">Sector data not fetched yet.</div>';
	}
	if ( $a['limit'] ) {
		$rows = array_slice( $rows, 0, absint( $a['limit'] ) );
	}
	ob_start(); ?>
	<div class="fiif-answer">
		<p>This table shows where FIIs are putting money <strong>across sectors</strong> — recent fortnight flow, 1-year flow,
		how much of each sector FIIs own, and their alpha (out/under-performance). Green = inflow, red = outflow.</p>
	</div>
	<table class="fiif-table fiif-sectors">
		<thead><tr>
			<th>Sector</th><th>Fortnight</th><th>1-Year</th><th>FII Own %</th><th>AUM %</th><th>Alpha</th>
		</tr></thead>
		<tbody>
		<?php foreach ( $rows as $r ) : ?>
			<tr>
				<td style="text-align:left"><?php echo esc_html( $r->name ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->fortnight_cr ); ?></td>
				<td><?php echo fiif_fmt_cr( $r->one_year_cr ); ?></td>
				<td><?php echo esc_html( number_format( $r->fii_own, 1 ) ); ?>%</td>
				<td><?php echo esc_html( number_format( $r->aum_pct, 1 ) ); ?>%</td>
				<td class="<?php echo $r->alpha >= 0 ? 'fiif-pos' : 'fiif-neg'; ?>"><?php echo ( $r->alpha >= 0 ? '+' : '' ) . number_format( $r->alpha, 1 ); ?></td>
			</tr>
		<?php endforeach; ?>
		</tbody>
	</table>
	<p class="fiif-updated">Source: NSE / FPI fortnightly sector data.</p>
	<?php
	return ob_get_clean();
} );

/* ---------------- CALENDAR HEATMAP ---------------- */
add_shortcode( 'fii_calendar', function ( $atts ) {
	$a    = shortcode_atts( array( 'days' => 60 ), $atts );
	$rows = array_reverse( fiif_get_flows( absint( $a['days'] ) ) ); // oldest -> newest
	if ( ! $rows ) {
		return '<div class="fiif-empty">No data for calendar yet.</div>';
	}
	// Color intensity by magnitude.
	$max = 1;
	foreach ( $rows as $r ) { $max = max( $max, abs( (float) $r->fii_net ) ); }
	ob_start(); ?>
	<div class="fiif-cal">
		<?php foreach ( $rows as $r ) :
			$n = (float) $r->fii_net;
			$intensity = min( 1, abs( $n ) / $max );
			$alpha = 0.15 + 0.85 * $intensity;
			$color = $n >= 0 ? "rgba(22,163,74,$alpha)" : "rgba(220,38,38,$alpha)";
			$title = mysql2date( 'd M Y', $r->trade_date ) . ': ' . ( $n >= 0 ? '+' : '' ) . number_format( $n, 0 ) . ' Cr'; ?>
			<span class="fiif-cal-cell" style="background:<?php echo esc_attr( $color ); ?>" title="<?php echo esc_attr( $title ); ?>"></span>
		<?php endforeach; ?>
	</div>
	<div class="fiif-cal-legend">
		<span class="fiif-cal-key"><i class="fiif-swatch sell"></i> FII selling</span>
		<span class="fiif-cal-key"><i class="fiif-swatch buy"></i> FII buying</span>
		<span class="fiif-cal-hint">Hover any day for the exact value</span>
	</div>
	<?php
	return ob_get_clean();
} );

/* ---------------- STOCKS DIRECTORY ---------------- */
add_shortcode( 'stocks_directory', function () {
	$search = isset( $_GET['q'] ) ? sanitize_text_field( wp_unslash( $_GET['q'] ) ) : '';
	$sector = isset( $_GET['sector'] ) ? sanitize_text_field( wp_unslash( $_GET['sector'] ) ) : '';
	$page   = isset( $_GET['spage'] ) ? max( 1, absint( $_GET['spage'] ) ) : 1;

	$rows = fiif_search_stocks( array(
		'search'   => $search,
		'sector'   => $sector,
		'per_page' => 50,
		'page'     => $page,
	) );
	$sectors = fiif_get_sectors();

	ob_start(); ?>
	<form class="fiif-dir-filter" method="get">
		<input type="text" name="q" value="<?php echo esc_attr( $search ); ?>" placeholder="Search company or symbol…">
		<select name="sector">
			<option value="">All sectors</option>
			<?php foreach ( $sectors as $s ) : ?>
				<option value="<?php echo esc_attr( $s ); ?>" <?php selected( $sector, $s ); ?>><?php echo esc_html( $s ); ?></option>
			<?php endforeach; ?>
		</select>
		<button type="submit">Search</button>
	</form>

	<?php if ( ! $rows ) : ?>
		<div class="fiif-empty">No stocks found. (Directory fills once data is fetched.)</div>
	<?php else : ?>
		<table class="fiif-table">
			<thead><tr><th>Symbol</th><th>Company</th><th>Sector</th><th>FII Holding</th></tr></thead>
			<tbody>
			<?php foreach ( $rows as $r ) :
				$slug = strtolower( $r->symbol ); ?>
				<tr>
					<td><a href="<?php echo esc_url( home_url( '/stocks/' . $slug . '/' ) ); ?>"><?php echo esc_html( $r->symbol ); ?></a></td>
					<td><?php echo esc_html( $r->company ); ?></td>
					<td><?php echo esc_html( $r->sector ); ?></td>
					<td><?php echo $r->fii_holding !== null ? esc_html( number_format( $r->fii_holding, 2 ) . '%' ) : '—'; ?></td>
				</tr>
			<?php endforeach; ?>
			</tbody>
		</table>
		<div class="fiif-pager">
			<?php if ( $page > 1 ) : ?>
				<a href="<?php echo esc_url( add_query_arg( 'spage', $page - 1 ) ); ?>">← Prev</a>
			<?php endif; ?>
			<?php if ( count( $rows ) === 50 ) : ?>
				<a href="<?php echo esc_url( add_query_arg( 'spage', $page + 1 ) ); ?>">Next →</a>
			<?php endif; ?>
		</div>
	<?php endif;
	return ob_get_clean();
} );
