<?php
/**
 * BFB one-time featured-image setter.
 * Images already live at /wp-content/uploads/bfb-articles/<file>.
 * For each of the 20 articles (matched by post slug), this registers the file
 * as a Media attachment and sets it as the post's featured image + alt text.
 *
 * HOW TO USE (one time):
 *  1. Upload this file to: /public_html/wp-content/themes/reviewshub/bfb-set-images.php
 *  2. In browser open: https://buyfrombest.com/wp-content/themes/reviewshub/bfb-set-images.php?key=bfb2026
 *  3. Read the report. When done, DELETE this file from the server.
 *
 * Safe to run more than once: it skips posts that already have a featured image.
 */

// load WordPress
$wp_load = dirname(__FILE__) . '/../../../wp-load.php';
if (!file_exists($wp_load)) { die('wp-load.php not found. Put this file inside the theme folder.'); }
require_once($wp_load);

if (!isset($_GET['key']) || $_GET['key'] !== 'bfb2026') {
    die('Forbidden. Add ?key=bfb2026 to the URL.');
}
if (!current_user_can('manage_options')) {
    // allow running while logged in as admin; otherwise still allow via key but warn
    echo "<p style='color:#a00'>Note: you are not detected as an admin. Make sure you are logged in to wp-admin in another tab.</p>";
}

require_once(ABSPATH . 'wp-admin/includes/image.php');
require_once(ABSPATH . 'wp-admin/includes/file.php');
require_once(ABSPATH . 'wp-admin/includes/media.php');

$uploads = wp_upload_dir();
$base_dir = trailingslashit($uploads['basedir']) . 'bfb-articles/media-upload/';
$base_url = trailingslashit($uploads['baseurl']) . 'bfb-articles/media-upload/';

// slug => image filename
$map = array(
  'best-websites-beginner-dirt-bikes' => 'beginner-dirt-bikes-featured.jpg',
  'best-websites-refurbished-electric-bikes' => 'refurbished-ebikes-featured.jpg',
  'best-websites-buy-utvs-side-by-sides' => 'utvs-featured.jpg',
  'best-websites-standby-generators' => 'standby-generators-featured.jpg',
  'best-websites-dirt-bike-gear-helmets' => 'dirt-bike-gear-featured.jpg',
  'best-websites-string-trimmers' => 'string-trimmers-featured.jpg',
  'best-websites-buy-jet-skis' => 'jet-skis-featured.jpg',
  'best-websites-portable-power-stations' => 'power-stations-featured.jpg',
  'best-websites-trailer-hitches' => 'trailer-hitches-featured.jpg',
  'best-websites-camping-coolers' => 'camping-coolers-featured.jpg',
  'best-websites-used-dirt-bikes' => 'used-dirt-bikes-featured.jpg',
  'best-websites-ebike-batteries' => 'ebike-batteries-featured.jpg',
  'best-websites-buy-trailers' => 'trailers-featured.jpg',
  'best-websites-robotic-lawn-mowers' => 'robotic-lawn-mowers-featured.jpg',
  'best-websites-off-road-recovery-gear' => 'recovery-gear-featured.jpg',
  'best-websites-commercial-pressure-washers' => 'commercial-pressure-washers-featured.jpg',
  'best-websites-atv-utv-parts' => 'atv-utv-parts-featured.jpg',
  'best-websites-emergency-backup-power' => 'emergency-backup-power-featured.jpg',
  'best-websites-tie-down-straps' => 'tie-down-straps-featured.jpg',
  'best-websites-floor-scrubbers' => 'floor-scrubbers-featured.jpg',
);

echo "<h2>BFB featured image setter</h2><pre style='font:13px monospace;line-height:1.5'>";

// ---- DIAGNOSTIC: show where we are looking and what's actually there ----
echo "LOOKING IN DIR: $base_dir\n";
echo "BASE URL:       $base_url\n";
echo "DIR EXISTS?     " . (is_dir($base_dir) ? 'YES' : 'NO') . "\n\n";
echo "Files actually found under uploads/bfb-articles (recursive):\n";
$found_any = false;
if (is_dir($base_dir)) {
    $rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($base_dir, FilesystemIterator::SKIP_DOTS));
    foreach ($rii as $f) {
        echo "   " . str_replace($base_dir, '', $f->getPathname()) . "\n";
        $found_any = true;
    }
}
if (!$found_any) {
    echo "   (nothing found here)\n";
    // try to locate the images anywhere under uploads
    echo "\nSearching whole uploads dir for *-featured.jpg ...\n";
    $up = $uploads['basedir'];
    $rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($up, FilesystemIterator::SKIP_DOTS));
    $hits = 0;
    foreach ($rii as $f) {
        $name = $f->getFilename();
        if (substr($name, -13) === '-featured.jpg' && $hits < 25) {
            echo "   FOUND: " . str_replace($up, '', $f->getPathname()) . "\n";
            $hits++;
        }
    }
    if ($hits === 0) echo "   (no *-featured.jpg anywhere under uploads)\n";
}
echo "\n----------------------------------------\n\n";
// ---- END DIAGNOSTIC ----


$done = 0; $skip = 0; $miss = 0; $err = 0;

foreach ($map as $slug => $file) {
    // find the post by slug (any status, including future/scheduled)
    $posts = get_posts(array(
        'name' => $slug,
        'post_type' => 'post',
        'post_status' => array('publish','future','draft','pending','private'),
        'numberposts' => 1,
    ));
    if (empty($posts)) { echo "MISS post not found: $slug\n"; $miss++; continue; }
    $post = $posts[0];
    $pid = $post->ID;

    // Check existing thumbnail: if it points to a MISSING attachment (broken import), fix it.
    $existing_thumb = get_post_meta($pid, '_thumbnail_id', true);
    if ($existing_thumb) {
        $thumb_post = get_post($existing_thumb);
        $thumb_file = $thumb_post ? get_attached_file($existing_thumb) : false;
        if ($thumb_post && $thumb_file && file_exists($thumb_file)) {
            echo "SKIP valid image already: $slug (#$pid) -> att #$existing_thumb\n"; $skip++; continue;
        }
        // broken: delete the bad meta and continue to set a real one
        delete_post_meta($pid, '_thumbnail_id');
        echo "FIX  broken thumb removed: $slug (#$pid) (was #$existing_thumb)\n";
    }

    $filepath = $base_dir . $file;
    if (!file_exists($filepath)) { echo "MISS file not found: $file\n"; $miss++; continue; }

    // is there already an attachment for this file? reuse it
    $existing = get_posts(array(
        'post_type' => 'attachment',
        'meta_key' => '_bfb_src',
        'meta_value' => $file,
        'numberposts' => 1,
        'fields' => 'ids',
    ));
    if (!empty($existing)) {
        $att_id = $existing[0];
    } else {
        $filetype = wp_check_filetype($file, null);
        $attachment = array(
            'guid'           => $base_url . $file,
            'post_mime_type' => $filetype['type'],
            'post_title'     => get_the_title($pid),
            'post_content'   => '',
            'post_status'    => 'inherit',
        );
        $att_id = wp_insert_attachment($attachment, $filepath, $pid);
        if (is_wp_error($att_id) || !$att_id) { echo "ERR insert failed: $slug\n"; $err++; continue; }
        $meta = wp_generate_attachment_metadata($att_id, $filepath);
        wp_update_attachment_metadata($att_id, $meta);
        update_post_meta($att_id, '_bfb_src', $file);
        update_post_meta($att_id, '_wp_attachment_image_alt', get_the_title($pid));
    }

    set_post_thumbnail($pid, $att_id);
    echo "OK  set image: $slug (#$pid) -> att #$att_id\n";
    $done++;
}

echo "\n=============================\n";
echo "DONE  set=$done  skipped=$skip  missing=$miss  errors=$err\n";
echo "=============================\n";
echo "\nAb is file ko server se DELETE kar do (security).\n";
echo "</pre>";
