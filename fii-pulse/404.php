<?php
if ( ! defined( 'ABSPATH' ) ) { exit; }
get_header();
?>
<main class="fp-main">
	<div class="fp-container">
		<div class="fp-page" style="text-align:center">
			<h1>Page not found</h1>
			<p>The page you’re looking for doesn’t exist. Try the FII/DII data or browse stocks.</p>
			<div class="fp-cta" style="justify-content:center;display:flex;gap:12px">
				<a class="fp-btn fp-btn-primary" href="<?php echo esc_url( home_url( '/fii-dii-data/' ) ); ?>">FII/DII Data</a>
				<a class="fp-btn fp-btn-ghost" style="background:#eef2ff;color:var(--brand)" href="<?php echo esc_url( home_url( '/' ) ); ?>">Home</a>
			</div>
		</div>
	</div>
</main>
<?php get_footer(); ?>
