<?php
/**
 * Page template — for shortcode pages (FII/DII, gainers, stocks, etc.) and static pages.
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }
get_header();
?>
<main class="fp-main">
	<div class="fp-container">
		<?php while ( have_posts() ) : the_post(); ?>
			<article class="fp-page">
				<nav class="fp-breadcrumb">
					<a href="<?php echo esc_url( home_url( '/' ) ); ?>">Home</a> › <?php the_title(); ?>
				</nav>
				<h1><?php the_title(); ?></h1>
				<div class="fp-content">
					<?php the_content(); ?>
				</div>
			</article>
		<?php endwhile; ?>
	</div>
</main>
<?php get_footer(); ?>
