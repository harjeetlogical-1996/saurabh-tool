<?php
/**
 * Homepage — FII dashboard (clean, icon-based, no emojis).
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }
get_header();

$flow = fp_latest_flow();
list( $mood, $mood_class ) = fp_mood();
$fno = function_exists( 'fiif_get_latest_fno' ) ? fiif_get_latest_fno() : null;
?>

<section class="fp-hero">
	<div class="fp-container">
		<div class="fp-hero-inner">
			<div>
				<span class="fp-hero-eyebrow"><?php echo fp_icon( 'globe', 15 ); ?> NSE · End-of-day data</span>
				<h1>Track where India's big money moves.</h1>
				<p>Daily FII &amp; DII flows, F&amp;O positioning, sector rotation and market sentiment — updated after every market close.</p>
				<div class="fp-cta">
					<a class="fp-btn fp-btn-primary" href="<?php echo esc_url( home_url( '/fii-dii-data/' ) ); ?>">View FII/DII Data <?php echo fp_icon( 'arrow-right', 17 ); ?></a>
					<a class="fp-btn fp-btn-ghost" href="#sectors">Sector Flows</a>
				</div>
			</div>
			<?php if ( $flow ) : ?>
			<div class="fp-hero-card">
				<div class="fp-hc-row">
					<span>FII Net</span>
					<strong class="<?php echo $flow->fii_net >= 0 ? 'up' : 'down'; ?>"><?php echo esc_html( fp_cr( $flow->fii_net ) ); ?></strong>
				</div>
				<div class="fp-hc-row">
					<span>DII Net</span>
					<strong class="<?php echo $flow->dii_net >= 0 ? 'up' : 'down'; ?>"><?php echo esc_html( fp_cr( $flow->dii_net ) ); ?></strong>
				</div>
				<div class="fp-hc-row">
					<span>Market Mood</span>
					<strong class="<?php echo esc_attr( $mood_class ); ?>"><?php echo esc_html( $mood ); ?></strong>
				</div>
				<div class="fp-hc-foot">As of <?php echo esc_html( mysql2date( 'd M Y', $flow->trade_date ) ); ?></div>
			</div>
			<?php endif; ?>
		</div>
	</div>
</section>

<main class="fp-main">
	<div class="fp-container">

		<?php if ( $flow ) : ?>
		<!-- Stat cards -->
		<section class="fp-section">
			<div class="fp-grid fp-grid-3">
				<div class="fp-card fp-stat">
					<div class="fp-stat-top">
						<span class="label">FII Net Today</span>
						<span class="fp-ico-badge <?php echo $flow->fii_net >= 0 ? 'b-up' : 'b-down'; ?>"><?php echo fp_icon( $flow->fii_net >= 0 ? 'trending-up' : 'trending-down', 18 ); ?></span>
					</div>
					<span class="value <?php echo esc_attr( fp_dir_class( $flow->fii_net ) ); ?>"><?php echo esc_html( fp_cr( $flow->fii_net ) ); ?></span>
					<span class="sub">Buy &#8377;<?php echo number_format( $flow->fii_buy, 0 ); ?> Cr &middot; Sell &#8377;<?php echo number_format( $flow->fii_sell, 0 ); ?> Cr</span>
				</div>
				<div class="fp-card fp-stat">
					<div class="fp-stat-top">
						<span class="label">DII Net Today</span>
						<span class="fp-ico-badge <?php echo $flow->dii_net >= 0 ? 'b-up' : 'b-down'; ?>"><?php echo fp_icon( $flow->dii_net >= 0 ? 'trending-up' : 'trending-down', 18 ); ?></span>
					</div>
					<span class="value <?php echo esc_attr( fp_dir_class( $flow->dii_net ) ); ?>"><?php echo esc_html( fp_cr( $flow->dii_net ) ); ?></span>
					<span class="sub">Buy &#8377;<?php echo number_format( $flow->dii_buy, 0 ); ?> Cr &middot; Sell &#8377;<?php echo number_format( $flow->dii_sell, 0 ); ?> Cr</span>
				</div>
				<div class="fp-card fp-stat">
					<div class="fp-stat-top">
						<span class="label">Market Mood</span>
						<span class="fp-ico-badge <?php echo $mood_class === 'up' ? 'b-up' : ( $mood_class === 'down' ? 'b-down' : 'b-flat' ); ?>"><?php echo fp_icon( 'gauge', 18 ); ?></span>
					</div>
					<span class="value <?php echo esc_attr( $mood_class ); ?>"><?php echo esc_html( $mood ); ?></span>
					<span class="sub">Cash net <?php echo $fno ? '&amp; F&amp;O ratio ' . number_format( $fno->long_short_ratio, 2 ) : 'direction'; ?></span>
				</div>
			</div>
		</section>
		<?php endif; ?>

		<!-- Streak -->
		<section class="fp-section">
			<?php echo do_shortcode( '[fii_streak]' ); ?>
		</section>

		<!-- Period stats -->
		<section class="fp-section">
			<?php echo do_shortcode( '[fii_stats]' ); ?>
		</section>

		<!-- Chart + mood -->
		<section class="fp-section">
			<div class="fp-grid fp-grid-hero">
				<div class="fp-card">
					<div class="fp-card-head">
						<h3><?php echo fp_icon( 'bar-chart' ); ?> FII/DII Net Flow &mdash; 30 Days</h3>
						<a href="<?php echo esc_url( home_url( '/fii-dii-data/' ) ); ?>">Full data <?php echo fp_icon( 'arrow-right', 15 ); ?></a>
					</div>
					<?php echo do_shortcode( '[fii_dii_chart days="30"]' ); ?>
				</div>
				<div class="fp-card">
					<div class="fp-card-head"><h3><?php echo fp_icon( 'gauge' ); ?> Today's Read</h3></div>
					<?php echo do_shortcode( '[fii_mood]' ); ?>
					<?php if ( $flow ) : ?>
					<p class="fp-note">
						On <?php echo esc_html( mysql2date( 'd M Y', $flow->trade_date ) ); ?>, FIIs were
						<strong><?php echo $flow->fii_net >= 0 ? 'net buyers' : 'net sellers'; ?></strong>
						and DIIs were
						<strong><?php echo $flow->dii_net >= 0 ? 'net buyers' : 'net sellers'; ?></strong>.
						Net flow = gross buy &minus; gross sell; positive is bullish, negative is caution.
					</p>
					<?php endif; ?>
				</div>
			</div>
		</section>

		<!-- Calendar heatmap -->
		<section class="fp-section">
			<div class="fp-card">
				<div class="fp-card-head"><h3><?php echo fp_icon( 'calendar' ); ?> FII Activity Heatmap &mdash; 60 Days</h3></div>
				<?php echo do_shortcode( '[fii_calendar days="60"]' ); ?>
			</div>
		</section>

		<!-- Sector flows -->
		<section class="fp-section" id="sectors">
			<div class="fp-card">
				<div class="fp-card-head"><h3><?php echo fp_icon( 'layers' ); ?> Where FIIs Are Moving &mdash; By Sector</h3></div>
				<?php echo do_shortcode( '[fii_sectors limit="12"]' ); ?>
			</div>
		</section>

		<!-- Recent flows -->
		<section class="fp-section">
			<div class="fp-card">
				<div class="fp-card-head">
					<h3><?php echo fp_icon( 'activity' ); ?> Recent FII/DII Activity</h3>
					<a href="<?php echo esc_url( home_url( '/fii-dii-data/' ) ); ?>">30-day table <?php echo fp_icon( 'arrow-right', 15 ); ?></a>
				</div>
				<?php echo do_shortcode( '[fii_dii_table days="10"]' ); ?>
			</div>
		</section>

		<!-- Education -->
		<section class="fp-section">
			<div class="fp-grid fp-grid-2">
				<div class="fp-card">
					<div class="fp-card-head"><h3><?php echo fp_icon( 'book' ); ?> How to Read FII/DII Data</h3></div>
					<p class="fp-note">FII and DII flows together signal market direction. The four combinations:</p>
					<ul class="fp-list">
						<li><strong>FII buy + DII buy</strong> &mdash; strong, broad-based rally</li>
						<li><strong>FII sell + DII sell</strong> &mdash; clear bearish trend</li>
						<li><strong>FII sell + DII buy</strong> &mdash; range-bound (DIIs absorb selling)</li>
						<li><strong>FII buy + DII sell</strong> &mdash; cautious up move</li>
					</ul>
				</div>
				<div class="fp-card">
					<div class="fp-card-head"><h3><?php echo fp_icon( 'globe' ); ?> What is FII?</h3></div>
					<p class="fp-note">FII (Foreign Institutional Investor), also called FPI, is an investment fund registered outside India that invests in Indian stocks, bonds and derivatives. Consistent FII inflows usually lift the market; sustained outflows pressure it. FIIs are among the largest movers of Indian equities, so tracking their daily activity gives an early read on sentiment.</p>
				</div>
			</div>
		</section>

		<!-- FAQ -->
		<section class="fp-section">
			<div class="fp-card">
				<div class="fp-card-head"><h3><?php echo fp_icon( 'help' ); ?> Frequently Asked Questions</h3></div>
				<div class="fp-faq">
					<details open>
						<summary>What does "FII net" mean?</summary>
						<p>FII net = FII gross buy &minus; FII gross sell for the day, in &#8377; crore. A positive number means FIIs bought more than they sold (bullish); negative means they sold more (bearish).</p>
					</details>
					<details>
						<summary>Is this data real-time?</summary>
						<p>No. FII/DII activity is published by NSE after market close each trading day (end-of-day). This site updates automatically every evening with the latest official figures.</p>
					</details>
					<details>
						<summary>Why do FIIs matter so much?</summary>
						<p>FIIs control a large share of free-float in Indian large-caps. When they buy or sell in size, indices like the Nifty often move with them &mdash; which is why their flows are watched closely.</p>
					</details>
					<details>
						<summary>What is the FII long/short ratio?</summary>
						<p>In F&amp;O, it compares FII long positions to short positions. Above 1 = net long (bullish bias); below 1 = net short (bearish bias).</p>
					</details>
				</div>
			</div>
		</section>

	</div>
</main>

<?php get_footer(); ?>
