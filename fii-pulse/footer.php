<?php
/**
 * Footer: links, disclaimer, copyright.
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }
?>
<footer class="fp-footer">
	<div class="fp-container">
		<div class="fp-foot-grid">
			<div>
				<h4><?php echo esc_html( get_bloginfo( 'name' ) ?: 'FII Pulse' ); ?></h4>
				<p>Daily FII/DII flows, F&amp;O positions, top gainers &amp; losers, and a full NSE stocks directory — updated every trading day from NSE end-of-day data.</p>
				<p class="fp-disclaimer"><strong>Disclaimer:</strong> This site is for educational and informational purposes only and is not investment advice. Data is end-of-day and sourced from NSE; it may be delayed or revised. Always consult a SEBI-registered advisor before investing.</p>
			</div>
			<div>
				<h4>Data</h4>
				<ul>
					<li><a href="<?php echo esc_url( home_url( '/fii-dii-data/' ) ); ?>">FII/DII Data</a></li>
					<li><a href="<?php echo esc_url( home_url( '/fii-fno-data/' ) ); ?>">F&amp;O Data</a></li>
					<li><a href="<?php echo esc_url( home_url( '/top-gainers/' ) ); ?>">Top Gainers</a></li>
					<li><a href="<?php echo esc_url( home_url( '/top-losers/' ) ); ?>">Top Losers</a></li>
					<li><a href="<?php echo esc_url( home_url( '/stocks/' ) ); ?>">Stocks Directory</a></li>
				</ul>
			</div>
			<div>
				<h4>Company</h4>
				<ul>
					<?php if ( has_nav_menu( 'footer' ) ) {
						wp_nav_menu( array( 'theme_location' => 'footer', 'container' => false, 'items_wrap' => '%3$s', 'depth' => 1 ) );
					} else { ?>
						<li><a href="<?php echo esc_url( home_url( '/about/' ) ); ?>">About</a></li>
						<li><a href="<?php echo esc_url( home_url( '/contact/' ) ); ?>">Contact</a></li>
						<li><a href="<?php echo esc_url( home_url( '/disclaimer/' ) ); ?>">Disclaimer</a></li>
						<li><a href="<?php echo esc_url( home_url( '/privacy-policy/' ) ); ?>">Privacy Policy</a></li>
					<?php } ?>
				</ul>
			</div>
		</div>

		<div class="fp-foot-bottom">
			<span>© <?php echo esc_html( gmdate( 'Y' ) ); ?> <?php echo esc_html( get_bloginfo( 'name' ) ?: 'FII Pulse' ); ?>. All rights reserved.</span>
			<span>Data source: NSE (end-of-day) · Not investment advice</span>
		</div>
	</div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
