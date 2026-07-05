<?php
/**
 * Plugin Name: WaterGuide SEO REST Bridge
 * Description: Exposes the theme's SEO custom fields (meta title, description,
 *              keywords, canonical, OG, etc.) to the WordPress REST API so they
 *              can be read & edited via REST (used by the WP MCP server).
 * Version: 1.1
 * Author: Saurabh
 *
 * INSTALL: Upload this file to  wp-content/mu-plugins/  (create the folder if it
 * doesn't exist). mu-plugins auto-activate — no activation needed.
 */

if (!defined('ABSPATH')) { exit; }

/**
 * 1) DIAGNOSTIC ENDPOINT
 *    GET /wp-json/wg-seo/v1/keys?post=ID
 *    Returns every custom-field (meta) key+value stored on that post, so we can
 *    discover the exact names of your SEO fields.
 */
add_action('rest_api_init', function () {
    register_rest_route('wg-seo/v1', '/keys', [
        'methods'  => 'GET',
        'permission_callback' => function () { return current_user_can('edit_posts'); },
        'callback' => function (WP_REST_Request $req) {
            $post_id = (int) $req->get_param('post');
            if (!$post_id) {
                // pick the most recent post if none given
                $recent = get_posts(['numberposts' => 1, 'post_status' => 'any']);
                if ($recent) { $post_id = $recent[0]->ID; }
            }
            $all = get_post_meta($post_id);
            $out = [];
            foreach ($all as $key => $vals) {
                $out[$key] = is_array($vals) ? array_map(function ($v) {
                    return mb_substr((string) $v, 0, 300);
                }, $vals) : $vals;
            }
            return ['post_id' => $post_id, 'meta_keys' => $out];
        },
    ]);

    /**
     * 2) GENERIC GET/SET for any meta key
     *    GET  /wg-seo/v1/meta?post=ID&key=KEYNAME
     *    POST /wg-seo/v1/meta   body: {post, key, value}
     */
    /**
     * 3) BULK CLEANUP — delete leftover _aioseo_* meta from all posts.
     *    GET  /wg-seo/v1/aioseo-scan         -> count posts that still have _aioseo_ data
     *    POST /wg-seo/v1/aioseo-clean        -> delete every _aioseo_* meta key (all posts)
     */
    register_rest_route('wg-seo/v1', '/aioseo-scan', [
        'methods'  => 'GET',
        'permission_callback' => function () { return current_user_can('manage_options'); },
        'callback' => function () {
            global $wpdb;
            $rows = $wpdb->get_results(
                "SELECT meta_key, COUNT(*) AS c FROM {$wpdb->postmeta}
                 WHERE meta_key LIKE '\_aioseo\_%' GROUP BY meta_key", ARRAY_A);
            $total = $wpdb->get_var(
                "SELECT COUNT(*) FROM {$wpdb->postmeta} WHERE meta_key LIKE '\_aioseo\_%'");
            return ['aioseo_meta_rows' => (int) $total, 'by_key' => $rows];
        },
    ]);
    register_rest_route('wg-seo/v1', '/aioseo-clean', [
        'methods'  => 'POST',
        'permission_callback' => function () { return current_user_can('manage_options'); },
        'callback' => function () {
            global $wpdb;
            $deleted = $wpdb->query(
                "DELETE FROM {$wpdb->postmeta} WHERE meta_key LIKE '\_aioseo\_%'");
            return ['deleted_rows' => (int) $deleted, 'done' => true];
        },
    ]);

    /**
     * 4) ONE-SHOT MIGRATION — copy old AIOSEO (_aioseo_*) meta into the theme's
     *    _cwg_seo_* fields, in a single pass over all posts/pages.
     *    POST /wg-seo/v1/migrate   body: {apply: bool}
     *      - apply=false (default) -> DRY RUN: report only, writes nothing.
     *      - apply=true            -> actually writes.
     *    Rules (safe by design):
     *      - Only writes where the target _cwg_seo_* field is EMPTY (never
     *        overwrites SEO you set manually).
     *      - Resolves AIOSEO template tags (#post_title #separator_sa #site_title)
     *        so stored values are real text, not raw tags.
     *      - Flags any entry that still contains template tags after resolving.
     */
    register_rest_route('wg-seo/v1', '/migrate', [
        'methods'  => 'POST',
        'permission_callback' => function () { return current_user_can('manage_options'); },
        'callback' => function (WP_REST_Request $req) {
            $b     = $req->get_json_params();
            $apply = ! empty($b['apply']);

            // AIOSEO source -> theme target. keywords maps to BOTH focus_kw (first
            // keyword) and the full keywords field.
            $map = [
                '_aioseo_title'            => '_cwg_seo_title',
                '_aioseo_description'      => '_cwg_seo_description',
                '_aioseo_og_title'         => '_cwg_seo_og_title',
                '_aioseo_og_description'   => '_cwg_seo_og_desc',
                '_aioseo_twitter_title'    => '_cwg_seo_twitter_title',
                '_aioseo_twitter_description' => '_cwg_seo_twitter_desc',
            ];

            $site_title = get_bloginfo('name');

            // Resolve common AIOSEO template tags into real text for a given post.
            $resolve = function ($val, $post_id) use ($site_title) {
                if (!is_string($val) || $val === '') { return $val; }
                $pairs = [
                    '#post_title'      => get_the_title($post_id),
                    '#page_title'      => get_the_title($post_id),
                    '#site_title'      => $site_title,
                    '#separator_sa'    => '-',
                    '#tagline'         => get_bloginfo('description'),
                    '#author_name'     => get_the_author_meta('display_name', (int) get_post_field('post_author', $post_id)),
                ];
                $val = strtr($val, $pairs);
                // Collapse whitespace left by removed tags.
                $val = trim(preg_replace('/\s{2,}/', ' ', $val));
                return $val;
            };

            $paged      = 1;
            $migrated   = 0;   // fields written (or would-be written)
            $skipped    = 0;   // target already had data
            $no_source  = 0;   // source empty
            $posts_hit  = 0;
            $flagged    = [];  // entries that still contain #tags after resolve
            $per_field  = [];

            do {
                $q = new WP_Query([
                    'post_type'      => ['post', 'page'],
                    'post_status'    => 'any',
                    'posts_per_page' => 100,
                    'paged'          => $paged,
                    'fields'         => 'ids',
                    'no_found_rows'  => true,
                ]);
                $ids = $q->posts;
                foreach ($ids as $pid) {
                    $touched = false;

                    // Keywords: AIOSEO stores them; take first as focus, all as keywords.
                    $kw_raw = get_post_meta($pid, '_aioseo_keywords', true);
                    if (is_string($kw_raw) && $kw_raw !== '') {
                        // AIOSEO may store JSON like [{"label":"x"}]; try to normalize.
                        $kw_list = [];
                        $maybe = json_decode($kw_raw, true);
                        if (is_array($maybe)) {
                            foreach ($maybe as $item) {
                                if (is_array($item) && isset($item['label'])) { $kw_list[] = $item['label']; }
                                elseif (is_string($item)) { $kw_list[] = $item; }
                            }
                        } else {
                            $kw_list = array_map('trim', explode(',', $kw_raw));
                        }
                        $kw_list = array_values(array_filter(array_map('trim', $kw_list)));
                        if ($kw_list) {
                            // focus keyword = first
                            $existing_focus = get_post_meta($pid, '_cwg_seo_focus_kw', true);
                            if ($existing_focus === '' || $existing_focus === null) {
                                if ($apply) { update_post_meta($pid, '_cwg_seo_focus_kw', $kw_list[0]); }
                                $migrated++; $touched = true;
                                $per_field['_cwg_seo_focus_kw'] = ($per_field['_cwg_seo_focus_kw'] ?? 0) + 1;
                            } else { $skipped++; }
                            // full keywords list
                            $existing_kw = get_post_meta($pid, '_cwg_seo_keywords', true);
                            if ($existing_kw === '' || $existing_kw === null) {
                                if ($apply) { update_post_meta($pid, '_cwg_seo_keywords', implode(', ', $kw_list)); }
                                $migrated++; $touched = true;
                                $per_field['_cwg_seo_keywords'] = ($per_field['_cwg_seo_keywords'] ?? 0) + 1;
                            } else { $skipped++; }
                        }
                    }

                    foreach ($map as $from => $to) {
                        $src = get_post_meta($pid, $from, true);
                        if ($src === '' || $src === null) { $no_source++; continue; }

                        $existing = get_post_meta($pid, $to, true);
                        if ($existing !== '' && $existing !== null) { $skipped++; continue; }

                        $clean = $resolve($src, $pid);
                        if (strpos($clean, '#') !== false) {
                            // Unknown template tag survived - flag it, still store best-effort.
                            $flagged[] = ['post' => $pid, 'field' => $to, 'value' => mb_substr($clean, 0, 120)];
                        }
                        if ($apply) { update_post_meta($pid, $to, $clean); }
                        $migrated++; $touched = true;
                        $per_field[$to] = ($per_field[$to] ?? 0) + 1;
                    }

                    if ($touched) { $posts_hit++; }
                }
                $paged++;
            } while (!empty($ids));

            return [
                'apply'            => $apply,
                'mode'             => $apply ? 'APPLIED' : 'DRY-RUN (nothing written)',
                'fields_migrated'  => $migrated,
                'posts_affected'   => $posts_hit,
                'skipped_existing' => $skipped,
                'source_empty'     => $no_source,
                'per_field'        => $per_field,
                'template_flagged' => $flagged,
                'note'             => $apply
                    ? 'Migration applied. Verify a few posts, then you may clean AIOSEO leftovers.'
                    : 'Dry run only. Re-POST with {"apply": true} to write.',
            ];
        },
    ]);

    register_rest_route('wg-seo/v1', '/meta', [
        [
            'methods'  => 'GET',
            'permission_callback' => function () { return current_user_can('edit_posts'); },
            'callback' => function (WP_REST_Request $req) {
                $post_id = (int) $req->get_param('post');
                $key     = sanitize_text_field($req->get_param('key'));
                return ['post_id' => $post_id, 'key' => $key,
                        'value' => get_post_meta($post_id, $key, true)];
            },
        ],
        [
            'methods'  => 'POST',
            'permission_callback' => function () { return current_user_can('edit_posts'); },
            'callback' => function (WP_REST_Request $req) {
                $b = $req->get_json_params();
                $post_id = (int) ($b['post'] ?? 0);
                $key     = sanitize_text_field($b['key'] ?? '');
                $value   = $b['value'] ?? '';
                if (!$post_id || !$key) {
                    return new WP_Error('bad', 'post and key required', ['status' => 400]);
                }
                update_post_meta($post_id, $key, $value);
                return ['post_id' => $post_id, 'key' => $key,
                        'value' => get_post_meta($post_id, $key, true), 'saved' => true];
            },
        ],
    ]);
});
