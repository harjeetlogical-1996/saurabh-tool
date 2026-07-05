<?php
/**
 * Fallback index — blog list / archives.
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }
get_header();
?>
<main class="fp-main">
	<div class="fp-container">
		<div class="fp-section-head"><h2><?php is_home() ? bloginfo( 'name' ) : the_archive_title(); ?></h2></div>
		<?php if ( have_posts() ) : ?>
			<div class="fp-grid fp-grid-3">
				<?php while ( have_posts() ) : the_post(); ?>
					<article class="fp-card">
						<h3 style="margin-top:0"><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h3>
						<p style="font-size:14px;color:var(--ink-soft)"><?php echo esc_html( wp_trim_words( get_the_excerpt(), 22 ) ); ?></p>
						<a href="<?php the_permalink(); ?>">Read more →</a>
					</article>
				<?php endwhile; ?>
			</div>
			<div style="margin-top:24px"><?php the_posts_pagination(); ?></div>
		<?php else : ?>
			<div class="fp-card">No posts yet.</div>
		<?php endif; ?>
	</div>
</main>
<?php get_footer(); ?>
