<?php
/**
 * Storage layer — create tables + save/read helpers.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Create all custom tables.
 */
function fiif_create_tables() {
	global $wpdb;
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	$charset = $wpdb->get_charset_collate();

	// 1) FII/DII cash flows (one row per date).
	$t_flows = fiif_table( 'flows' );
	$sql1 = "CREATE TABLE $t_flows (
		trade_date DATE NOT NULL,
		fii_buy DECIMAL(14,2) DEFAULT 0,
		fii_sell DECIMAL(14,2) DEFAULT 0,
		fii_net DECIMAL(14,2) DEFAULT 0,
		dii_buy DECIMAL(14,2) DEFAULT 0,
		dii_sell DECIMAL(14,2) DEFAULT 0,
		dii_net DECIMAL(14,2) DEFAULT 0,
		updated_at DATETIME DEFAULT NULL,
		PRIMARY KEY  (trade_date)
	) $charset;";

	// 2) FII F&O / participant-wise positions (one row per date).
	$t_fno = fiif_table( 'fno' );
	$sql2 = "CREATE TABLE $t_fno (
		trade_date DATE NOT NULL,
		idx_fut_long DECIMAL(14,2) DEFAULT 0,
		idx_fut_short DECIMAL(14,2) DEFAULT 0,
		stock_fut_long DECIMAL(14,2) DEFAULT 0,
		stock_fut_short DECIMAL(14,2) DEFAULT 0,
		idx_call_long DECIMAL(14,2) DEFAULT 0,
		idx_call_short DECIMAL(14,2) DEFAULT 0,
		idx_put_long DECIMAL(14,2) DEFAULT 0,
		idx_put_short DECIMAL(14,2) DEFAULT 0,
		long_short_ratio DECIMAL(8,4) DEFAULT 0,
		updated_at DATETIME DEFAULT NULL,
		PRIMARY KEY  (trade_date)
	) $charset;";

	// 3) Stocks master list (the directory).
	$t_stocks = fiif_table( 'stocks' );
	$sql3 = "CREATE TABLE $t_stocks (
		symbol VARCHAR(32) NOT NULL,
		company VARCHAR(191) DEFAULT '',
		sector VARCHAR(96) DEFAULT '',
		series VARCHAR(8) DEFAULT 'EQ',
		isin VARCHAR(20) DEFAULT '',
		fii_holding DECIMAL(6,2) DEFAULT NULL,
		fii_holding_quarter VARCHAR(12) DEFAULT '',
		updated_at DATETIME DEFAULT NULL,
		PRIMARY KEY  (symbol),
		KEY company (company)
	) $charset;";

	// 4) Daily stock snapshot (price/volume/change) — for gainers/losers + stock pages.
	$t_quotes = fiif_table( 'quotes' );
	$sql4 = "CREATE TABLE $t_quotes (
		symbol VARCHAR(32) NOT NULL,
		trade_date DATE NOT NULL,
		ltp DECIMAL(14,2) DEFAULT 0,
		prev_close DECIMAL(14,2) DEFAULT 0,
		pct_change DECIMAL(8,2) DEFAULT 0,
		volume BIGINT DEFAULT 0,
		traded_value DECIMAL(18,2) DEFAULT 0,
		week52_high DECIMAL(14,2) DEFAULT 0,
		week52_low DECIMAL(14,2) DEFAULT 0,
		updated_at DATETIME DEFAULT NULL,
		PRIMARY KEY  (symbol, trade_date),
		KEY pct_change (pct_change),
		KEY trade_date (trade_date)
	) $charset;";

	// 5) Sector-wise FII flows (one row per sector, latest snapshot).
	$t_sectors = fiif_table( 'sectors' );
	$sql5 = "CREATE TABLE $t_sectors (
		name VARCHAR(120) NOT NULL,
		aum_pct DECIMAL(6,2) DEFAULT 0,
		fortnight_cr DECIMAL(14,2) DEFAULT 0,
		one_year_cr DECIMAL(14,2) DEFAULT 0,
		fii_own DECIMAL(6,2) DEFAULT 0,
		alpha DECIMAL(6,2) DEFAULT 0,
		history_json TEXT,
		last_date VARCHAR(20) DEFAULT '',
		updated_at DATETIME DEFAULT NULL,
		PRIMARY KEY  (name)
	) $charset;";

	dbDelta( $sql1 );
	dbDelta( $sql2 );
	dbDelta( $sql3 );
	dbDelta( $sql4 );
	dbDelta( $sql5 );

	update_option( 'fiif_db_version', FIIF_DB_VERSION );
}

/* ---------------- SAVE HELPERS ---------------- */

/**
 * Upsert one FII/DII flows row. $row keys match column names (without trade_date logic).
 */
function fiif_save_flows( $trade_date, $row ) {
	global $wpdb;
	$data = array_merge(
		array(
			'trade_date' => $trade_date,
			'updated_at' => current_time( 'mysql' ),
		),
		$row
	);
	$wpdb->replace( fiif_table( 'flows' ), $data );
}

function fiif_save_fno( $trade_date, $row ) {
	global $wpdb;
	$data = array_merge(
		array(
			'trade_date' => $trade_date,
			'updated_at' => current_time( 'mysql' ),
		),
		$row
	);
	$wpdb->replace( fiif_table( 'fno' ), $data );
}

function fiif_save_stock( $symbol, $row ) {
	global $wpdb;
	$data = array_merge(
		array(
			'symbol'     => $symbol,
			'updated_at' => current_time( 'mysql' ),
		),
		$row
	);
	$wpdb->replace( fiif_table( 'stocks' ), $data );
}

function fiif_save_quote( $symbol, $trade_date, $row ) {
	global $wpdb;
	$data = array_merge(
		array(
			'symbol'     => $symbol,
			'trade_date' => $trade_date,
			'updated_at' => current_time( 'mysql' ),
		),
		$row
	);
	$wpdb->replace( fiif_table( 'quotes' ), $data );
}

/* ---------------- READ HELPERS ---------------- */

/**
 * Latest N flows rows (most recent first).
 */
function fiif_get_flows( $limit = 30 ) {
	global $wpdb;
	$limit = absint( $limit );
	return $wpdb->get_results(
		$wpdb->prepare( "SELECT * FROM " . fiif_table( 'flows' ) . " ORDER BY trade_date DESC LIMIT %d", $limit )
	);
}

function fiif_get_latest_flow() {
	$rows = fiif_get_flows( 1 );
	return $rows ? $rows[0] : null;
}

function fiif_get_latest_fno() {
	global $wpdb;
	return $wpdb->get_row( "SELECT * FROM " . fiif_table( 'fno' ) . " ORDER BY trade_date DESC LIMIT 1" );
}

/**
 * Top movers for the latest available date. $dir = 'gainers' | 'losers' | 'active'.
 */
function fiif_get_movers( $dir = 'gainers', $limit = 20 ) {
	global $wpdb;
	$limit = absint( $limit );
	$qt    = fiif_table( 'quotes' );

	$latest = $wpdb->get_var( "SELECT MAX(trade_date) FROM $qt" );
	if ( ! $latest ) {
		return array();
	}

	if ( 'active' === $dir ) {
		$order = 'traded_value DESC';
	} elseif ( 'losers' === $dir ) {
		$order = 'pct_change ASC';
	} else {
		$order = 'pct_change DESC';
	}

	return $wpdb->get_results(
		$wpdb->prepare(
			"SELECT q.*, s.company, s.sector FROM $qt q
			 LEFT JOIN " . fiif_table( 'stocks' ) . " s ON s.symbol = q.symbol
			 WHERE q.trade_date = %s ORDER BY $order LIMIT %d",
			$latest,
			$limit
		)
	);
}

/**
 * Directory search. $args: search, sector, orderby, order, per_page, page.
 */
function fiif_search_stocks( $args = array() ) {
	global $wpdb;
	$d = wp_parse_args( $args, array(
		'search'   => '',
		'sector'   => '',
		'orderby'  => 'company',
		'order'    => 'ASC',
		'per_page' => 50,
		'page'     => 1,
	) );

	$st = fiif_table( 'stocks' );
	$where  = ' WHERE 1=1';
	$params = array();

	if ( $d['search'] !== '' ) {
		$like     = '%' . $wpdb->esc_like( $d['search'] ) . '%';
		$where   .= ' AND (symbol LIKE %s OR company LIKE %s)';
		$params[] = $like;
		$params[] = $like;
	}
	if ( $d['sector'] !== '' ) {
		$where   .= ' AND sector = %s';
		$params[] = $d['sector'];
	}

	$allowed_orderby = array( 'company', 'symbol', 'sector', 'fii_holding' );
	$orderby = in_array( $d['orderby'], $allowed_orderby, true ) ? $d['orderby'] : 'company';
	$order   = strtoupper( $d['order'] ) === 'DESC' ? 'DESC' : 'ASC';

	$per  = max( 1, absint( $d['per_page'] ) );
	$page = max( 1, absint( $d['page'] ) );
	$off  = ( $page - 1 ) * $per;

	$sql  = "SELECT * FROM $st $where ORDER BY $orderby $order LIMIT %d OFFSET %d";
	$params[] = $per;
	$params[] = $off;

	return $wpdb->get_results( $wpdb->prepare( $sql, $params ) );
}

function fiif_get_stock( $symbol ) {
	global $wpdb;
	return $wpdb->get_row(
		$wpdb->prepare( "SELECT * FROM " . fiif_table( 'stocks' ) . " WHERE symbol = %s", strtoupper( $symbol ) )
	);
}

function fiif_get_sectors() {
	global $wpdb;
	return $wpdb->get_col( "SELECT DISTINCT sector FROM " . fiif_table( 'stocks' ) . " WHERE sector <> '' ORDER BY sector ASC" );
}

/* ---------------- SECTOR FLOWS ---------------- */

function fiif_save_sector( $name, $row ) {
	global $wpdb;
	$data = array_merge(
		array( 'name' => $name, 'updated_at' => current_time( 'mysql' ) ),
		$row
	);
	$wpdb->replace( fiif_table( 'sectors' ), $data );
}

/** All sector rows, optionally ordered. $order = 'fortnight'|'year'|'own'|'alpha'. */
function fiif_get_sector_flows( $order = 'fortnight' ) {
	global $wpdb;
	$map = array(
		'fortnight' => 'fortnight_cr DESC',
		'year'      => 'one_year_cr DESC',
		'own'       => 'fii_own DESC',
		'alpha'     => 'alpha DESC',
		'aum'       => 'aum_pct DESC',
	);
	$ord = isset( $map[ $order ] ) ? $map[ $order ] : $map['fortnight'];
	return $wpdb->get_results( "SELECT * FROM " . fiif_table( 'sectors' ) . " ORDER BY $ord" );
}

/* ---------------- ANALYTICS (computed from flows) ---------------- */

/**
 * Current FII (or DII) buy/sell streak length + direction.
 * Returns array( 'days' => int, 'dir' => 'buying'|'selling'|'flat' ).
 */
function fiif_streak( $who = 'fii' ) {
	$rows = fiif_get_flows( 60 ); // newest first
	if ( ! $rows ) {
		return array( 'days' => 0, 'dir' => 'flat' );
	}
	$col   = $who === 'dii' ? 'dii_net' : 'fii_net';
	$first = (float) $rows[0]->$col;
	if ( $first == 0 ) {
		return array( 'days' => 0, 'dir' => 'flat' );
	}
	$dir   = $first > 0 ? 'buying' : 'selling';
	$days  = 0;
	foreach ( $rows as $r ) {
		$v = (float) $r->$col;
		if ( ( $dir === 'buying' && $v > 0 ) || ( $dir === 'selling' && $v < 0 ) ) {
			$days++;
		} else {
			break;
		}
	}
	return array( 'days' => $days, 'dir' => $dir );
}

/**
 * Totals over the last N days for fii/dii net.
 */
function fiif_period_totals( $days = 30 ) {
	global $wpdb;
	$days = absint( $days );
	$row  = $wpdb->get_row( $wpdb->prepare(
		"SELECT SUM(fii_net) AS fii, SUM(dii_net) AS dii, COUNT(*) AS n
		 FROM ( SELECT fii_net, dii_net FROM " . fiif_table( 'flows' ) . " ORDER BY trade_date DESC LIMIT %d ) t",
		$days
	) );
	return $row ? $row : (object) array( 'fii' => 0, 'dii' => 0, 'n' => 0 );
}

/**
 * Month-by-month FII/DII net totals (most recent months first).
 */
function fiif_monthly_totals( $months = 6 ) {
	global $wpdb;
	$months = absint( $months );
	return $wpdb->get_results( $wpdb->prepare(
		"SELECT DATE_FORMAT(trade_date, '%%Y-%%m') AS ym,
		        SUM(fii_net) AS fii_net, SUM(dii_net) AS dii_net, COUNT(*) AS days
		 FROM " . fiif_table( 'flows' ) . "
		 GROUP BY ym ORDER BY ym DESC LIMIT %d",
		$months
	) );
}

/**
 * Highest single-day FII buy and sell in the dataset.
 */
function fiif_extremes() {
	global $wpdb;
	$t = fiif_table( 'flows' );
	return array(
		'max_buy'  => $wpdb->get_row( "SELECT trade_date, fii_net FROM $t ORDER BY fii_net DESC LIMIT 1" ),
		'max_sell' => $wpdb->get_row( "SELECT trade_date, fii_net FROM $t ORDER BY fii_net ASC LIMIT 1" ),
	);
}
