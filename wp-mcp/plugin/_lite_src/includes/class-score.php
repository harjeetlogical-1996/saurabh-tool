<?php
/**
 * SEO score analysis. Pure function that scores a post against its focus
 * keyword and returns a 0-100 score plus a list of checks (Yoast-style).
 * Used by both the REST API and the admin meta box (via JS mirror).
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WPPSEO_Score {

	/**
	 * Analyze a post. Returns array( score, grade, checks[] ).
	 */
	public static function analyze( $post_id ) {
		$focus   = wppseo_get( $post_id, 'focus_kw' );
		$title   = wppseo_get( $post_id, 'title' );
		if ( ! $title ) {
			$title = get_the_title( $post_id );
		}
		$desc    = wppseo_get( $post_id, 'description' );
		$content = wp_strip_all_tags( get_post_field( 'post_content', $post_id ) );
		$slug    = get_post_field( 'post_name', $post_id );
		$has_img = has_post_thumbnail( $post_id );

		return self::score_text( $focus, $title, $desc, $content, $slug, $has_img );
	}

	/**
	 * Stateless scorer (also reusable by the MCP server for previews).
	 */
	public static function score_text( $focus, $title, $desc, $content, $slug, $has_img ) {
		$checks = array();
		$focus_l = strtolower( trim( $focus ) );
		$words   = str_word_count( $content );

		$add = function ( $ok, $label, $weight ) use ( &$checks ) {
			$checks[] = array( 'ok' => (bool) $ok, 'label' => $label, 'weight' => $weight );
		};

		if ( '' === $focus_l ) {
			return array(
				'score'  => 0,
				'grade'  => 'none',
				'checks' => array( array( 'ok' => false, 'label' => 'Set a focus keyword to analyze this page.', 'weight' => 0 ) ),
			);
		}

		// Title checks.
		$add( false !== strpos( strtolower( $title ), $focus_l ), 'Focus keyword appears in the SEO title', 15 );
		$tlen = mb_strlen( $title );
		$add( $tlen >= 40 && $tlen <= 60, 'SEO title length is good (40-60 chars)', 10 );

		// Description checks.
		$add( $desc && false !== strpos( strtolower( $desc ), $focus_l ), 'Focus keyword appears in the meta description', 12 );
		$dlen = mb_strlen( $desc );
		$add( $dlen >= 120 && $dlen <= 160, 'Meta description length is good (120-160 chars)', 10 );

		// Slug.
		$add( false !== strpos( strtolower( $slug ), str_replace( ' ', '-', $focus_l ) ), 'Focus keyword appears in the URL slug', 8 );

		// Content checks.
		$add( $words >= 300, 'Content is at least 300 words', 12 );
		$first = strtolower( mb_substr( $content, 0, 200 ) );
		$add( false !== strpos( $first, $focus_l ), 'Focus keyword appears early in the content', 10 );

		// Keyword density 0.5%-2.5%.
		$density = $words > 0 ? ( substr_count( strtolower( $content ), $focus_l ) / $words ) * 100 : 0;
		$add( $density >= 0.5 && $density <= 2.5, sprintf( 'Keyword density is healthy (%.1f%%)', $density ), 13 );

		// Image.
		$add( $has_img, 'Page has a featured image', 10 );

		// Total.
		$max = 0;
		$got = 0;
		foreach ( $checks as $c ) {
			$max += $c['weight'];
			if ( $c['ok'] ) {
				$got += $c['weight'];
			}
		}
		$score = $max > 0 ? (int) round( $got / $max * 100 ) : 0;
		$grade = $score >= 80 ? 'good' : ( $score >= 50 ? 'ok' : 'poor' );

		return array( 'score' => $score, 'grade' => $grade, 'checks' => $checks );
	}
}
