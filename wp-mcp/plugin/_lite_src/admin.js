(function () {
	'use strict';
	var $ = function (s, r) { return (r || document).querySelector(s); };
	var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

	var box = $('.wppseo-wrap');
	if (!box) return;

	// Tabs
	$$('.wppseo-tab', box).forEach(function (tab) {
		tab.addEventListener('click', function () {
			$$('.wppseo-tab', box).forEach(function (t) { t.classList.remove('active'); });
			$$('.wppseo-panel', box).forEach(function (p) { p.hidden = true; });
			tab.classList.add('active');
			var panel = $('.wppseo-panel[data-panel="' + tab.dataset.tab + '"]', box);
			if (panel) panel.hidden = false;
		});
	});

	var titleEl = $('#wppseo-title'), descEl = $('#wppseo-desc'), focusEl = $('#wppseo-focus');
	var prevTitle = $('#wppseo-prev-title'), prevDesc = $('#wppseo-prev-desc');
	var tCount = $('#wppseo-title-count'), dCount = $('#wppseo-desc-count');

	function postContent() {
		// Classic editor
		var ta = document.getElementById('content');
		if (ta && ta.value) return ta.value;
		// Block editor
		if (window.wp && wp.data && wp.data.select('core/editor')) {
			try { return wp.data.select('core/editor').getEditedPostContent() || ''; } catch (e) {}
		}
		return '';
	}
	function postSlug() {
		if (window.wp && wp.data && wp.data.select('core/editor')) {
			try { return wp.data.select('core/editor').getEditedPostSlug() || ''; } catch (e) {}
		}
		var s = document.getElementById('post_name');
		return s ? s.value : '';
	}
	function hasImage() {
		if (window.wp && wp.data && wp.data.select('core/editor')) {
			try { return !!wp.data.select('core/editor').getEditedPostAttribute('featured_media'); } catch (e) {}
		}
		return !!document.querySelector('#postimagediv img');
	}
	function strip(html) { var d = document.createElement('div'); d.innerHTML = html; return (d.textContent || '').trim(); }

	function counter(el, val, lo, hi) {
		if (!el) return;
		var n = val.length;
		el.textContent = n;
		el.className = 'wppseo-count ' + (n >= lo && n <= hi ? 'good' : (n ? 'bad' : ''));
	}

	function analyze() {
		var focus = (focusEl ? focusEl.value : '').trim().toLowerCase();
		var title = (titleEl ? titleEl.value : '') || '';
		var desc = (descEl ? descEl.value : '') || '';
		var content = strip(postContent());
		var slug = postSlug();
		var words = content ? content.split(/\s+/).length : 0;

		var scoreBox = $('#wppseo-score'), scoreText = $('.wppseo-score-text', scoreBox), checksEl = $('#wppseo-checks');
		if (!focus) {
			scoreBox.className = 'wppseo-score';
			scoreText.textContent = 'Enter a focus keyword to see your SEO score.';
			checksEl.innerHTML = '';
			return;
		}

		var checks = [];
		function add(ok, label, w) { checks.push({ ok: ok, label: label, w: w }); }
		add(title.toLowerCase().indexOf(focus) > -1, 'Focus keyword in SEO title', 15);
		add(title.length >= 40 && title.length <= 60, 'SEO title length 40-60 chars', 10);
		add(desc.toLowerCase().indexOf(focus) > -1, 'Focus keyword in meta description', 12);
		add(desc.length >= 120 && desc.length <= 160, 'Meta description 120-160 chars', 10);
		add(slug.indexOf(focus.replace(/\s+/g, '-')) > -1, 'Focus keyword in URL slug', 8);
		add(words >= 300, 'Content at least 300 words', 12);
		add(content.slice(0, 200).toLowerCase().indexOf(focus) > -1, 'Keyword appears early in content', 10);
		var density = words ? ((content.toLowerCase().split(focus).length - 1) / words) * 100 : 0;
		add(density >= 0.5 && density <= 2.5, 'Keyword density healthy (' + density.toFixed(1) + '%)', 13);
		add(hasImage(), 'Page has a featured image', 10);

		var max = 0, got = 0;
		checks.forEach(function (c) { max += c.w; if (c.ok) got += c.w; });
		var score = max ? Math.round(got / max * 100) : 0;
		var grade = score >= 80 ? 'good' : (score >= 50 ? 'ok' : 'poor');

		scoreBox.className = 'wppseo-score ' + grade;
		scoreText.textContent = 'SEO score: ' + score + ' / 100 (' + grade + ')';
		checksEl.innerHTML = checks.map(function (c) {
			return '<li class="' + (c.ok ? 'ok' : 'bad') + '">' + c.label + '</li>';
		}).join('');
	}

	function refresh() {
		if (titleEl) { prevTitle.textContent = titleEl.value || 'SEO title preview'; counter(tCount, titleEl.value, 40, 60); }
		if (descEl) { prevDesc.textContent = descEl.value || 'Your meta description preview will appear here.'; counter(dCount, descEl.value, 120, 160); }
		analyze();
	}

	[titleEl, descEl, focusEl].forEach(function (el) {
		if (el) el.addEventListener('input', refresh);
	});
	refresh();
	setInterval(analyze, 2500); // pick up content/slug/image changes
})();
