<?php
/**
 * AI SEO Score - computes a modern, AI-era SEO scorecard for THIS site, right
 * inside WordPress. 5 categories (each 0-100) + overall:
 *   On-Page, Technical, AEO (answer-engine), GEO (AI-citation), Authority (E-E-A-T).
 *
 * Everything is MEASURED from the site's own published content (no external APIs).
 * Also stores a daily snapshot so the "This period" report can show before->after.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_AiSeo {

	/** Filler words that never count as an anchor/topic on their own. */
	private static function stopwords() {
		return array_flip( array(
			'the','a','an','and','or','for','to','of','in','on','with','you','your',
			'is','are','was','be','this','that','it','how','what','why','best','top',
			'ideas','guide','tips','ways','things','easy','simple','new','more','most',
			'now','today','like','great','good','very','how-to','step','steps',
		) );
	}

	/** Compute the full scorecard for up to $limit published posts. */
	public static function score( $limit = 50 ) {
		$q = new WP_Query( array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => $limit,
			'no_found_rows'  => true,
		) );
		$posts = $q->posts;
		$n = max( 1, count( $posts ) );

		$sum = array( 'on_page' => 0, 'technical' => 0, 'aeo' => 0, 'geo' => 0, 'authority_eeat' => 0 );
		$missing_meta = $missing_alt = $no_schema = $thin = 0;
		$all_links = array();
		$post_urls = array();

		foreach ( $posts as $p ) {
			$raw   = $p->post_content;
			$text  = wp_strip_all_tags( $raw );
			$words = str_word_count( $text );
			$lower = strtolower( $text );

			// headings, images, lists, tables, faq, links
			preg_match_all( '/<h([1-6])[^>]*>(.*?)<\/h\1>/is', $raw, $hm );
			$headings = isset( $hm[2] ) ? $hm[2] : array();
			$q_headings = 0;
			foreach ( $headings as $h ) {
				$ht = trim( wp_strip_all_tags( $h ) );
				if ( substr( $ht, -1 ) === '?' || preg_match( '/^(how|what|why|when|where|who|which|is|are|can|do)\b/i', $ht ) ) {
					$q_headings++;
				}
			}
			preg_match_all( '/<img\b[^>]*>/i', $raw, $imgs_m );
			$imgs = isset( $imgs_m[0] ) ? $imgs_m[0] : array();
			$imgs_no_alt = 0;
			foreach ( $imgs as $img ) {
				if ( ! preg_match( '/alt=["\'][^"\']+["\']/i', $img ) ) {
					$imgs_no_alt++;
				}
			}
			$missing_alt += $imgs_no_alt;
			$n_lists  = preg_match_all( '/<(ul|ol)\b/i', $raw, $x );
			$n_tables = preg_match_all( '/<table\b/i', $raw, $x );
			$has_faq  = ( strpos( $lower, 'faq' ) !== false || strpos( $lower, 'frequently asked' ) !== false
				|| stripos( $raw, 'faqpage' ) !== false );

			// facts / vague
			$fact_hits = preg_match_all( '/\b\d[\d,\.]*%?\b|\$\d[\d,\.]*/', $text, $x );
			$has_year  = preg_match( '/\b(19|20)\d{2}\b/', $text );
			$vague     = 0;
			foreach ( array( 'many businesses','a lot of','some people','studies show','experts say','generally','often' ) as $v ) {
				$vague += substr_count( $lower, $v );
			}

			// sources / authority / definition
			$home    = wp_parse_url( home_url(), PHP_URL_HOST );
			preg_match_all( '/href=["\']https?:\/\/([^"\'\/]+)/i', $raw, $lm );
			$ext_domains = array();
			foreach ( ( isset( $lm[1] ) ? $lm[1] : array() ) as $d ) {
				if ( $d !== $home ) { $ext_domains[ $d ] = 1; }
			}
			$cite = 0;
			foreach ( array( 'according to','source:','study','research','report','published','journal','university' ) as $w ) {
				$cite += substr_count( $lower, $w );
			}
			$authority = 0;
			foreach ( array( 'author','reviewed by','written by','expert','phd','certified','years of experience','fact-checked' ) as $w ) {
				$authority += substr_count( $lower, $w );
			}
			$definition = preg_match( '/\b[A-Z][a-z ]{3,40}\b (is|are|refers to|means) /', $text );

			$schema_blocks = preg_match_all( '/<script[^>]*application\/ld\+json[^>]*>.*?<\/script>/is', $raw, $x );

			// ---- category scores ----
			$op = 0;
			$op += $words >= 600 ? 25 : ( $words >= 300 ? 12 : 0 );
			$op += $headings ? 20 : 0;
			$op += ( $imgs && ! $imgs_no_alt ) ? 20 : ( $imgs ? 8 : 0 );
			$internal = preg_match_all( '/href=["\'](\/|' . preg_quote( home_url(), '/' ) . ')/i', $raw, $x );
			$op += $internal >= 2 ? 20 : ( $internal ? 10 : 0 );
			$op += trim( $p->post_excerpt ) ? 15 : 0;
			$sum['on_page'] += min( 100, $op );
			if ( $words < 300 ) { $thin++; }

			$t = 0;
			$t += $schema_blocks ? 40 : 0;
			$t += $headings ? 30 : 0;
			$t += ( $words && count( $headings ) && ( $words / max( 1, count( $headings ) ) < 400 ) ) ? 30 : 10;
			$sum['technical'] += min( 100, $t );
			if ( ! $schema_blocks ) { $no_schema++; }

			$a = 0;
			$a += $has_faq ? 30 : 0;
			$a += $q_headings ? 25 : 0;
			$a += ( $n_lists || $n_tables ) ? 20 : 0;
			$a += $definition ? 25 : 0;
			$sum['aeo'] += min( 100, $a );

			$g = 0;
			$g += $definition ? 20 : 0;
			$g += min( 30, $fact_hits * 4 );
			$g -= $vague * 4;
			$g += count( $ext_domains ) * 12 + $cite * 6;
			$g += $q_headings ? 10 : 0;
			$g += $has_year ? 10 : 0;
			$sum['geo'] += max( 0, min( 100, $g ) );

			$au = 0;
			$au += min( 60, $authority * 18 );
			$au += $has_year ? 25 : 0;
			$au += $cite ? 15 : 0;
			$sum['authority_eeat'] += min( 100, $au );

			// meta description present?
			$desc = get_post_meta( $p->ID, wppseo_key( 'description' ), true );
			if ( ! trim( (string) $desc ) ) { $missing_meta++; }

			// orphan tracking
			$post_urls[ $p->ID ] = untrailingslashit( get_permalink( $p ) );
			preg_match_all( '/href=["\']([^"\']+)["\']/i', $raw, $hrefs );
			foreach ( ( isset( $hrefs[1] ) ? $hrefs[1] : array() ) as $h ) {
				$h = untrailingslashit( $h );
				if ( strpos( $h, home_url() ) === 0 ) { $all_links[ $h ] = 1; }
				elseif ( strpos( $h, '/' ) === 0 ) { $all_links[ untrailingslashit( home_url() ) . $h ] = 1; }
			}
		}

		$orphans = 0;
		foreach ( $post_urls as $u ) {
			if ( $u && ! isset( $all_links[ $u ] ) ) { $orphans++; }
		}

		$cats = array();
		foreach ( $sum as $k => $v ) {
			$cats[ $k ] = (int) round( $v / $n );
		}
		$overall = (int) round( array_sum( $cats ) / count( $cats ) );

		$result = array(
			'overall'    => $overall,
			'categories' => $cats,
			'issues'     => array(
				'missing_meta_description' => $missing_meta,
				'images_missing_alt'       => $missing_alt,
				'posts_without_schema'     => $no_schema,
				'thin_posts'               => $thin,
				'orphan_pages'             => $orphans,
			),
			'posts_scored' => count( $posts ),
		);

		self::snapshot( $result );
		return $result;
	}

	/** Save one snapshot per day (for the before -> after report). */
	private static function snapshot( $result ) {
		$hist = get_option( 'wppseo_score_history', array() );
		$hist = is_array( $hist ) ? $hist : array();
		$today = gmdate( 'Y-m-d' );
		$hist[ $today ] = array( 'overall' => $result['overall'], 'categories' => $result['categories'] );
		// keep the last 60 days
		if ( count( $hist ) > 60 ) {
			$hist = array_slice( $hist, -60, 60, true );
		}
		update_option( 'wppseo_score_history', $hist );
	}

	/** Latest + a ~7-day-ago snapshot for the report card. */
	public static function report() {
		$hist = get_option( 'wppseo_score_history', array() );
		$hist = is_array( $hist ) ? $hist : array();
		if ( ! $hist ) {
			return array( 'latest' => null, 'before' => null );
		}
		ksort( $hist );
		$keys   = array_keys( $hist );
		$latest = $hist[ end( $keys ) ];
		$before = null;
		$cutoff = gmdate( 'Y-m-d', strtotime( '-7 days' ) );
		foreach ( $keys as $k ) {
			if ( $k <= $cutoff ) { $before = $hist[ $k ]; }
		}
		if ( null === $before && count( $keys ) > 1 ) {
			$before = $hist[ $keys[0] ];
		}
		return array( 'latest' => $latest, 'before' => $before );
	}
}
