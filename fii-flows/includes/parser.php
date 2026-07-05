<?php
/**
 * Parser layer — turn raw CSV / JSON text into clean numeric rows.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Convert a string like "1,234.56" or "(123.45)" or "-" into a float.
 */
function fiif_num( $val ) {
	$val = trim( (string) $val );
	if ( $val === '' || $val === '-' || strtoupper( $val ) === 'N/A' ) {
		return 0.0;
	}
	$neg = false;
	if ( strpos( $val, '(' ) !== false ) { // (123) = negative accounting style
		$neg = true;
	}
	$val = preg_replace( '/[^0-9.\-]/', '', $val ); // strip commas, brackets, ₹, etc.
	$f   = (float) $val;
	return $neg ? -abs( $f ) : $f;
}

/**
 * Parse CSV text into array of associative rows using the header line.
 * Tolerant of NSE's leading blank lines / titles.
 */
function fiif_parse_csv( $text ) {
	$text  = str_replace( array( "\r\n", "\r" ), "\n", $text );
	$lines = array_values( array_filter( explode( "\n", $text ), function ( $l ) {
		return trim( $l ) !== '';
	} ) );
	if ( count( $lines ) < 2 ) {
		return array();
	}

	// Find the header row: the first line that has >= 2 comma-separated cells with letters.
	$header_idx = 0;
	foreach ( $lines as $i => $line ) {
		$cells = str_getcsv( $line );
		if ( count( $cells ) >= 2 && preg_match( '/[A-Za-z]/', $line ) ) {
			$header_idx = $i;
			break;
		}
	}

	$header = array_map( function ( $h ) {
		return strtolower( trim( $h ) );
	}, str_getcsv( $lines[ $header_idx ] ) );

	$rows = array();
	for ( $i = $header_idx + 1; $i < count( $lines ); $i++ ) {
		$cells = str_getcsv( $lines[ $i ] );
		if ( count( $cells ) < 2 ) {
			continue;
		}
		$row = array();
		foreach ( $header as $j => $key ) {
			$row[ $key ] = isset( $cells[ $j ] ) ? trim( $cells[ $j ] ) : '';
		}
		$rows[] = $row;
	}
	return $rows;
}

/**
 * Find a value in a row by trying several possible column-name fragments.
 */
function fiif_pick( $row, $fragments ) {
	foreach ( $row as $key => $val ) {
		foreach ( (array) $fragments as $frag ) {
			if ( strpos( $key, $frag ) !== false ) {
				return $val;
			}
		}
	}
	return '';
}

/**
 * Normalize the FII/DII cash report rows into our flows columns.
 * Handles both the NSE shape and common GitHub-mirror JSON-ish shapes.
 *
 * Returns array( 'fii' => [...], 'dii' => [...] ) of numbers, or null.
 */
function fiif_normalize_flows_rows( $rows ) {
	$out = array(
		'fii_buy' => 0, 'fii_sell' => 0, 'fii_net' => 0,
		'dii_buy' => 0, 'dii_sell' => 0, 'dii_net' => 0,
	);
	$found = false;

	foreach ( $rows as $row ) {
		$category = strtolower( fiif_pick( $row, array( 'category', 'client', 'type', 'participant' ) ) );
		$buy  = fiif_num( fiif_pick( $row, array( 'buy value', 'gross purchase', 'buy', 'purchase' ) ) );
		$sell = fiif_num( fiif_pick( $row, array( 'sell value', 'gross sales', 'sell', 'sales' ) ) );
		$net  = fiif_num( fiif_pick( $row, array( 'net value', 'net' ) ) );
		if ( ! $net && ( $buy || $sell ) ) {
			$net = $buy - $sell;
		}

		if ( strpos( $category, 'fii' ) !== false || strpos( $category, 'fpi' ) !== false || strpos( $category, 'foreign' ) !== false ) {
			$out['fii_buy'] = $buy; $out['fii_sell'] = $sell; $out['fii_net'] = $net;
			$found = true;
		} elseif ( strpos( $category, 'dii' ) !== false || strpos( $category, 'domestic' ) !== false ) {
			$out['dii_buy'] = $buy; $out['dii_sell'] = $sell; $out['dii_net'] = $net;
			$found = true;
		}
	}

	return $found ? $out : null;
}

/**
 * Normalize participant-wise OI rows into FII F&O long/short columns.
 */
function fiif_normalize_fno_rows( $rows ) {
	foreach ( $rows as $row ) {
		$client = strtolower( fiif_pick( $row, array( 'client type', 'client', 'participant' ) ) );
		if ( strpos( $client, 'fii' ) === false && strpos( $client, 'foreign' ) === false ) {
			continue;
		}
		$idx_fut_long  = fiif_num( fiif_pick( $row, array( 'future index long', 'index future long' ) ) );
		$idx_fut_short = fiif_num( fiif_pick( $row, array( 'future index short', 'index future short' ) ) );
		$stk_fut_long  = fiif_num( fiif_pick( $row, array( 'future stock long', 'stock future long' ) ) );
		$stk_fut_short = fiif_num( fiif_pick( $row, array( 'future stock short', 'stock future short' ) ) );
		$call_long     = fiif_num( fiif_pick( $row, array( 'option index call long', 'index call long' ) ) );
		$call_short    = fiif_num( fiif_pick( $row, array( 'option index call short', 'index call short' ) ) );
		$put_long      = fiif_num( fiif_pick( $row, array( 'option index put long', 'index put long' ) ) );
		$put_short     = fiif_num( fiif_pick( $row, array( 'option index put short', 'index put short' ) ) );

		$total_long  = $idx_fut_long + $stk_fut_long + $call_long + $put_long;
		$total_short = $idx_fut_short + $stk_fut_short + $call_short + $put_short;
		$ratio       = $total_short > 0 ? round( $total_long / $total_short, 4 ) : 0;

		return array(
			'idx_fut_long'     => $idx_fut_long,
			'idx_fut_short'    => $idx_fut_short,
			'stock_fut_long'   => $stk_fut_long,
			'stock_fut_short'  => $stk_fut_short,
			'idx_call_long'    => $call_long,
			'idx_call_short'   => $call_short,
			'idx_put_long'     => $put_long,
			'idx_put_short'    => $put_short,
			'long_short_ratio' => $ratio,
		);
	}
	return null;
}
