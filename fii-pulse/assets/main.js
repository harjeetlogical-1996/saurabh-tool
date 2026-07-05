/* FII Pulse — mobile menu toggle */
( function () {
	document.addEventListener( 'DOMContentLoaded', function () {
		var burger = document.querySelector( '.fp-burger' );
		var nav    = document.querySelector( '.fp-nav' );
		if ( ! burger || ! nav ) { return; }
		burger.addEventListener( 'click', function () {
			var open = nav.classList.toggle( 'open' );
			burger.setAttribute( 'aria-expanded', open ? 'true' : 'false' );
		} );
	} );
} )();
