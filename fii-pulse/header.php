<?php
/**
 * Header: ticker bar + sticky nav.
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$flow = fp_latest_flow();
list( $mood, $mood_class ) = fp_mood();
?><!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>

<!-- Ticker -->
<div class="fp-ticker">
	<div class="fp-container">
		<?php if ( $flow ) : ?>
			<span>FII Net: <b class="<?php echo $flow->fii_net >= 0 ? 'up' : 'down'; ?>"><?php echo esc_html( fp_cr( $flow->fii_net ) ); ?></b></span>
			<span>DII Net: <b class="<?php echo $flow->dii_net >= 0 ? 'up' : 'down'; ?>"><?php echo esc_html( fp_cr( $flow->dii_net ) ); ?></b></span>
			<span>Mood: <b class="<?php echo esc_attr( $mood_class ); ?>"><?php echo esc_html( $mood ); ?></b></span>
			<span style="margin-left:auto;color:#64748b">As of <?php echo esc_html( mysql2date( 'd M Y', $flow->trade_date ) ); ?> · NSE EOD</span>
		<?php else : ?>
			<span>FII Pulse — daily FII/DII flows, F&amp;O & stocks</span>
		<?php endif; ?>
	</div>
</div>

<!-- Header -->
<header class="fp-header">
	<div class="fp-container">
		<a class="fp-logo" href="<?php echo esc_url( home_url( '/' ) ); ?>">
			<span class="dot"></span>
			<?php echo esc_html( get_bloginfo( 'name' ) ?: 'FII Pulse' ); ?>
		</a>

		<button class="fp-burger" aria-label="Menu" aria-expanded="false">
			<span></span><span></span><span></span>
		</button>

		<nav class="fp-nav" aria-label="Primary">
			<?php
			if ( has_nav_menu( 'primary' ) ) {
				wp_nav_menu( array( 'theme_location' => 'primary', 'container' => false, 'depth' => 1 ) );
			} else {
				fp_fallback_menu();
			}
			?>
		</nav>
	</div>
</header>
