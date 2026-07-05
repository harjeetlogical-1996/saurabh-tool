<?php
/**
 * Single post template (blog / educational articles).
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
				<p style="color:var(--muted);font-size:14px;margin-top:-6px">
					By <?php the_author(); ?> · Updated <?php echo esc_html( get_the_modified_date() ); ?>
				</p>
				<?php if ( has_post_thumbnail() ) : ?>
					<div style="margin:18px 0"><?php the_post_thumbnail( 'large', array( 'style' => 'border-radius:12px' ) ); ?></div>
				<?php endif; ?>
				<div class="fp-content">
					<?php the_content(); ?>
				</div>
			</article>
		<?php endwhile; ?>
	</div>
</main>
<?php get_footer(); ?>
