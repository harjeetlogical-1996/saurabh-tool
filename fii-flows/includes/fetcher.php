<?php
/**
 * Fetcher layer — get data from NSE (direct, with cookie+headers) and
 * fall back to a GitHub mirror if NSE blocks us.
 *
 * IMPORTANT: NSE protects endpoints with Cloudflare + cookies. We must first
 * hit the homepage to obtain cookies, then request the data endpoint with a
 * full browser-like header set and those cookies.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Browser-like headers NSE expects.
 */
function fiif_browser_headers( $referer = 'https://www.nseindia.com/' ) {
	return array(
		'User-Agent'      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
		'Accept'          => 'application/json, text/csv, text/plain, */*',
		'Accept-Language' => 'en-US,en;q=0.9',
		'Referer'         => $referer,
		'Connection'      => 'keep-alive',
	);
}

/**
 * Get NSE cookies by hitting the homepage. Cached in a transient for 30 min.
 * Returns a cookie string for the Cookie header, or '' on failure.
 */
function fiif_get_nse_cookies() {
	$cached = get_transient( 'fiif_nse_cookies' );
	if ( $cached ) {
		return $cached;
	}

	$resp = wp_remote_get( 'https://www.nseindia.com/', array(
		'timeout'    => 20,
		'headers'    => fiif_browser_headers(),
		'sslverify'  => true,
	) );

	if ( is_wp_error( $resp ) ) {
		return '';
	}

	$cookies = wp_remote_retrieve_cookies( $resp );
	if ( empty( $cookies ) ) {
		return '';
	}

	$pairs = array();
	foreach ( $cookies as $c ) {
		$pairs[] = $c->name . '=' . $c->value;
	}
	$cookie_str = implode( '; ', $pairs );
	set_transient( 'fiif_nse_cookies', $cookie_str, 30 * MINUTE_IN_SECONDS );
	return $cookie_str;
}

/**
 * GET a NSE URL with cookies + headers. Returns body string or WP_Error.
 */
function fiif_nse_get( $url, $referer = 'https://www.nseindia.com/' ) {
	$cookies = fiif_get_nse_cookies();
	$headers = fiif_browser_headers( $referer );
	if ( $cookies ) {
		$headers['Cookie'] = $cookies;
	}

	$resp = wp_remote_get( $url, array(
		'timeout'   => 25,
		'headers'   => $headers,
		'sslverify' => true,
	) );

	if ( is_wp_error( $resp ) ) {
		return $resp;
	}
	$code = wp_remote_retrieve_response_code( $resp );
	if ( $code !== 200 ) {
		return new WP_Error( 'fiif_http', 'NSE returned HTTP ' . $code . ' for ' . $url );
	}
	$body = wp_remote_retrieve_body( $resp );
	if ( ! $body ) {
		return new WP_Error( 'fiif_empty', 'Empty body from ' . $url );
	}
	return $body;
}

/**
 * Generic GET (for GitHub mirror, no cookies needed).
 */
function fiif_plain_get( $url ) {
	$resp = wp_remote_get( $url, array(
		'timeout'   => 25,
		'headers'   => array( 'User-Agent' => 'fii-flows-wp/' . FIIF_VERSION ),
		'sslverify' => true,
	) );
	if ( is_wp_error( $resp ) ) {
		return $resp;
	}
	$code = wp_remote_retrieve_response_code( $resp );
	if ( $code !== 200 ) {
		return new WP_Error( 'fiif_http', 'Mirror returned HTTP ' . $code );
	}
	return wp_remote_retrieve_body( $resp );
}

/* ------------------------------------------------------------------ */
/* SOURCES                                                            */
/* ------------------------------------------------------------------ */

// NSE endpoints (these are the public JSON/CSV report endpoints).
const FIIF_NSE_FIIDII   = 'https://www.nseindia.com/api/fiidiiTradeReact';
const FIIF_NSE_GAINERS  = 'https://www.nseindia.com/api/live-analysis-variations?index=gainers';
const FIIF_NSE_LOSERS   = 'https://www.nseindia.com/api/live-analysis-variations?index=loosers';

// GitHub mirror (MrChartist/fii-dii-data) — verified working JSON with FII/DII cash + F&O
// + PCR + sentiment, ~800 days history. This is our PRIMARY source (reliable, clean, complete).
const FIIF_MIRROR_HISTORY = 'https://raw.githubusercontent.com/MrChartist/fii-dii-data/main/data/history.json';
const FIIF_MIRROR_SECTORS = 'https://raw.githubusercontent.com/MrChartist/fii-dii-data/main/data/sectors.json';

/* ------------------------------------------------------------------ */
/* HIGH-LEVEL FETCHERS                                                */
/* ------------------------------------------------------------------ */

/**
 * Fetch FII/DII cash flows + F&O. PRIMARY source = GitHub mirror JSON (clean,
 * complete, reliable). Saves up to $days recent rows. Returns true/false.
 *
 * @param int $days How many recent days to import (default 90).
 */
function fiif_fetch_flows( $days = 90 ) {
	$body = fiif_plain_get( FIIF_MIRROR_HISTORY );

	// Optional: try NSE direct first only if reachable (kept as a best-effort extra).
	if ( is_wp_error( $body ) ) {
		fiif_log( 'flows: mirror failed - ' . $body->get_error_message() );
		// Last resort: NSE direct JSON (often blocked from some networks).
		$nse = fiif_nse_get( FIIF_NSE_FIIDII, 'https://www.nseindia.com/reports/fii-dii' );
		if ( ! is_wp_error( $nse ) ) {
			$json = json_decode( $nse, true );
			if ( is_array( $json ) && fiif_save_flows_from_nse_json( $json ) ) {
				fiif_log( 'flows: saved from NSE JSON (mirror was down)' );
				return true;
			}
		} else {
			fiif_log( 'flows: NSE also failed - ' . $nse->get_error_message() );
		}
		return false;
	}

	$json = json_decode( $body, true );
	if ( ! is_array( $json ) ) {
		fiif_log( 'flows: mirror JSON parse failed' );
		return false;
	}

	$days  = absint( $days );
	$count = 0;
	foreach ( $json as $item ) {
		if ( ! is_array( $item ) || empty( $item['date'] ) ) {
			continue;
		}
		$date = fiif_extract_date( $item['date'] );
		if ( ! $date ) {
			continue;
		}

		// Cash flows.
		fiif_save_flows( $date, array(
			'fii_buy'  => (float) ( $item['fii_buy'] ?? 0 ),
			'fii_sell' => (float) ( $item['fii_sell'] ?? 0 ),
			'fii_net'  => (float) ( $item['fii_net'] ?? 0 ),
			'dii_buy'  => (float) ( $item['dii_buy'] ?? 0 ),
			'dii_sell' => (float) ( $item['dii_sell'] ?? 0 ),
			'dii_net'  => (float) ( $item['dii_net'] ?? 0 ),
		) );

		// F&O (same record carries FII derivatives + PCR).
		$idx_fut_long  = (float) ( $item['fii_idx_fut_long'] ?? 0 );
		$idx_fut_short = (float) ( $item['fii_idx_fut_short'] ?? 0 );
		$stk_fut_long  = (float) ( $item['fii_stk_fut_long'] ?? 0 );
		$stk_fut_short = (float) ( $item['fii_stk_fut_short'] ?? 0 );
		$call_long     = (float) ( $item['fii_idx_call_long'] ?? 0 );
		$call_short    = (float) ( $item['fii_idx_call_short'] ?? 0 );
		$put_long      = (float) ( $item['fii_idx_put_long'] ?? 0 );
		$put_short     = (float) ( $item['fii_idx_put_short'] ?? 0 );
		$tot_long      = $idx_fut_long + $stk_fut_long + $call_long + $put_long;
		$tot_short     = $idx_fut_short + $stk_fut_short + $call_short + $put_short;
		$ratio         = $tot_short > 0 ? round( $tot_long / $tot_short, 4 ) : 0;

		// Only write an F&O row if there is any non-zero derivative data.
		if ( $tot_long || $tot_short ) {
			fiif_save_fno( $date, array(
				'idx_fut_long'     => $idx_fut_long,
				'idx_fut_short'    => $idx_fut_short,
				'stock_fut_long'   => $stk_fut_long,
				'stock_fut_short'  => $stk_fut_short,
				'idx_call_long'    => $call_long,
				'idx_call_short'   => $call_short,
				'idx_put_long'     => $put_long,
				'idx_put_short'    => $put_short,
				'long_short_ratio' => $ratio,
			) );
		}

		$count++;
		if ( $count >= $days ) {
			break;
		}
	}

	fiif_log( "flows: saved $count days from GitHub mirror" );
	return $count > 0;
}

/**
 * NSE fiidiiTradeReact returns an array of objects with category + buyValue/sellValue/netValue.
 */
function fiif_save_flows_from_nse_json( $json ) {
	$norm = array(
		'fii_buy' => 0, 'fii_sell' => 0, 'fii_net' => 0,
		'dii_buy' => 0, 'dii_sell' => 0, 'dii_net' => 0,
	);
	$date  = '';
	$found = false;

	foreach ( $json as $item ) {
		if ( ! is_array( $item ) ) {
			continue;
		}
		$cat = strtolower( $item['category'] ?? '' );
		$buy = fiif_num( $item['buyValue'] ?? '' );
		$sell = fiif_num( $item['sellValue'] ?? '' );
		$net = fiif_num( $item['netValue'] ?? '' );
		if ( ! $net && ( $buy || $sell ) ) {
			$net = $buy - $sell;
		}
		if ( ! $date && ! empty( $item['date'] ) ) {
			$date = fiif_extract_date( $item['date'] );
		}
		if ( strpos( $cat, 'fii' ) !== false || strpos( $cat, 'fpi' ) !== false ) {
			$norm['fii_buy'] = $buy; $norm['fii_sell'] = $sell; $norm['fii_net'] = $net; $found = true;
		} elseif ( strpos( $cat, 'dii' ) !== false ) {
			$norm['dii_buy'] = $buy; $norm['dii_sell'] = $sell; $norm['dii_net'] = $net; $found = true;
		}
	}

	if ( ! $date ) {
		$date = current_time( 'Y-m-d' );
	}
	if ( $found ) {
		fiif_save_flows( $date, $norm );
		return true;
	}
	return false;
}

/**
 * Fetch top gainers + losers from NSE and store as quotes.
 */
function fiif_fetch_movers() {
	$date  = current_time( 'Y-m-d' );
	$saved = 0;

	foreach ( array( FIIF_NSE_GAINERS, FIIF_NSE_LOSERS ) as $url ) {
		$body = fiif_nse_get( $url, 'https://www.nseindia.com/market-data/top-gainers-losers' );
		if ( is_wp_error( $body ) ) {
			fiif_log( 'movers: ' . $body->get_error_message() );
			continue;
		}
		$json = json_decode( $body, true );
		if ( ! is_array( $json ) ) {
			continue;
		}
		// NSE wraps lists under various keys (e.g. NIFTY, legends, data). Find the array of stock objects.
		$list = fiif_find_stock_array( $json );
		foreach ( $list as $s ) {
			if ( empty( $s['symbol'] ) ) {
				continue;
			}
			$symbol = strtoupper( $s['symbol'] );
			fiif_save_quote( $symbol, $date, array(
				'ltp'         => fiif_num( $s['ltp'] ?? $s['lastPrice'] ?? 0 ),
				'prev_close'  => fiif_num( $s['prev_price'] ?? $s['previousClose'] ?? 0 ),
				'pct_change'  => fiif_num( $s['perChange'] ?? $s['pChange'] ?? 0 ),
				'volume'      => (int) fiif_num( $s['trade_quantity'] ?? $s['totalTradedVolume'] ?? 0 ),
				'traded_value'=> fiif_num( $s['turnover'] ?? $s['totalTradedValue'] ?? 0 ),
			) );
			// Ensure the stock exists in the directory too.
			if ( ! fiif_get_stock( $symbol ) ) {
				fiif_save_stock( $symbol, array( 'company' => $s['symbol'] ) );
			}
			$saved++;
		}
	}
	fiif_log( "movers: saved $saved quotes" );
	return $saved > 0;
}

/**
 * Walk a decoded NSE JSON looking for the first array whose items have a 'symbol' key.
 */
function fiif_find_stock_array( $json ) {
	if ( isset( $json[0]['symbol'] ) ) {
		return $json;
	}
	foreach ( $json as $val ) {
		if ( is_array( $val ) ) {
			if ( isset( $val['data'] ) && is_array( $val['data'] ) && isset( $val['data'][0]['symbol'] ) ) {
				return $val['data'];
			}
			if ( isset( $val[0]['symbol'] ) ) {
				return $val;
			}
		}
	}
	return array();
}

/**
 * Convert various date strings into Y-m-d. Returns '' if unparseable.
 */
function fiif_extract_date( $str ) {
	$str = trim( (string) $str );
	if ( $str === '' ) {
		return '';
	}
	$ts = strtotime( $str );
	return $ts ? gmdate( 'Y-m-d', $ts ) : '';
}

/**
 * Run everything (called by cron + Fetch Now button).
 */
function fiif_fetch_all() {
	$results = array(
		'flows'   => fiif_fetch_flows( 120 ),
		'sectors' => fiif_fetch_sectors(),
		'movers'  => fiif_fetch_movers(), // best-effort; needs NSE reachable
	);
	update_option( 'fiif_last_run', current_time( 'mysql' ) );
	update_option( 'fiif_last_result', $results );
	return $results;
}

/**
 * Fetch sector-wise FII flows from the mirror sectors.json.
 */
function fiif_fetch_sectors() {
	$body = fiif_plain_get( FIIF_MIRROR_SECTORS );
	if ( is_wp_error( $body ) ) {
		fiif_log( 'sectors: failed - ' . $body->get_error_message() );
		return false;
	}
	$json = json_decode( $body, true );
	if ( ! is_array( $json ) ) {
		fiif_log( 'sectors: parse failed' );
		return false;
	}
	$count = 0;
	foreach ( $json as $s ) {
		if ( empty( $s['name'] ) ) {
			continue;
		}
		fiif_save_sector( $s['name'], array(
			'aum_pct'      => (float) ( $s['aumPct'] ?? 0 ),
			'fortnight_cr' => (float) ( $s['fortnightCr'] ?? 0 ),
			'one_year_cr'  => (float) ( $s['oneYearCr'] ?? 0 ),
			'fii_own'      => (float) ( $s['fiiOwn'] ?? 0 ),
			'alpha'        => (float) ( $s['alpha'] ?? 0 ),
			'history_json' => wp_json_encode( $s['historyCr'] ?? array() ),
			'last_date'    => sanitize_text_field( $s['lastDate'] ?? '' ),
		) );
		$count++;
	}
	fiif_log( "sectors: saved $count sectors" );
	return $count > 0;
}

/**
 * Tiny logger into an option (last 50 lines) for the admin screen.
 */
function fiif_log( $msg ) {
	$log = get_option( 'fiif_log', array() );
	if ( ! is_array( $log ) ) {
		$log = array();
	}
	array_unshift( $log, current_time( 'mysql' ) . '  ' . $msg );
	$log = array_slice( $log, 0, 50 );
	update_option( 'fiif_log', $log );
}
