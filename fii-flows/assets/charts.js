/* FII Flows — render net-flow trend charts from data-fiif-chart attributes. */
( function () {
	function render( canvas ) {
		var raw = canvas.getAttribute( 'data-fiif-chart' );
		if ( ! raw || typeof Chart === 'undefined' ) {
			return;
		}
		var d;
		try {
			d = JSON.parse( raw );
		} catch ( e ) {
			return;
		}

		new Chart( canvas.getContext( '2d' ), {
			type: 'bar',
			data: {
				labels: d.labels,
				datasets: [
					{
						label: 'FII Net (₹ Cr)',
						data: d.fii,
						backgroundColor: d.fii.map( function ( v ) {
							return v >= 0 ? 'rgba(22,163,74,0.7)' : 'rgba(220,38,38,0.7)';
						} )
					},
					{
						label: 'DII Net (₹ Cr)',
						data: d.dii,
						type: 'line',
						borderColor: 'rgba(37,99,235,0.9)',
						backgroundColor: 'rgba(37,99,235,0.2)',
						tension: 0.3,
						fill: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: { legend: { position: 'top' } },
				scales: { y: { title: { display: true, text: '₹ Crore' } } }
			}
		} );
	}

	document.addEventListener( 'DOMContentLoaded', function () {
		document.querySelectorAll( '.fiif-chart' ).forEach( render );
	} );
} )();
