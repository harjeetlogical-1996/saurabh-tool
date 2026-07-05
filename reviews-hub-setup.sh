#!/usr/bin/env bash
# =====================================================================
#  Reviews Hub — WordPress one-time setup script
#  Run this INSIDE Local's "Open site shell" after creating the site.
#  It uses wp-cli (bundled with Local).
#
#  HOW TO RUN:
#    1. In Local, right-click your site -> "Open site shell"
#    2. Navigate to where this file is, OR copy its contents and paste
#    3. Run:  bash reviews-hub-setup.sh
# =====================================================================

set -e

echo "=================================================="
echo " Reviews Hub setup starting..."
echo "=================================================="

# ---------------------------------------------------------------------
# 1. CATEGORIES + SUBCATEGORIES
#    Format: "Parent Category|Sub1,Sub2,Sub3,Sub4"
# ---------------------------------------------------------------------
CATEGORIES=(
  "Dirt Bikes & Motocross|Beginner Dirt Bikes,Kids Dirt Bikes,Electric Dirt Bikes,Gear & Helmets"
  "E-Bikes & E-Mobility|Commuter E-Bikes,Fat-Tire E-Bikes,Electric Scooters,Batteries & Chargers"
  "Powersports & Off-Road|ATVs,UTVs,Snowmobiles,Jet Skis"
  "Generators & Power|Portable Generators,Solar Generators,Standby Generators,Power Stations"
  "Lawn & Outdoor Power|Lawn Mowers,Chainsaws,Leaf Blowers,Trimmers"
  "Industrial Cleanup|Pressure Washers,Shop Vacs,Floor Scrubbers"
  "Hauling & Towing|Trailers,Hitches,Winches,Tie-Downs"
  "Camping & Overlanding|Portable Power Stations,Coolers,Rooftop Tents,Recovery Gear"
)

echo ""
echo ">> Creating categories and subcategories..."
for entry in "${CATEGORIES[@]}"; do
  parent="${entry%%|*}"
  subs="${entry#*|}"

  # Create parent category (skip if exists), capture its term ID
  parent_id=$(wp term create category "$parent" --porcelain 2>/dev/null \
              || wp term list category --name="$parent" --field=term_id --format=ids 2>/dev/null)
  echo "  [Category] $parent (id: $parent_id)"

  # Create each subcategory under the parent
  IFS=',' read -ra SUBARR <<< "$subs"
  for sub in "${SUBARR[@]}"; do
    wp term create category "$sub" --parent="$parent_id" >/dev/null 2>&1 \
      && echo "      - $sub" \
      || echo "      - $sub (already exists, skipped)"
  done
done

# ---------------------------------------------------------------------
# 2. ADSENSE-REQUIRED PAGES (drafts with starter content)
# ---------------------------------------------------------------------
echo ""
echo ">> Creating required pages (About, Contact, Privacy, Disclaimer)..."

create_page () {
  local title="$1"
  local content="$2"
  if wp post list --post_type=page --field=post_title --format=csv 2>/dev/null | grep -qx "$title"; then
    echo "  [Page] $title (already exists, skipped)"
  else
    wp post create --post_type=page --post_status=publish \
      --post_title="$title" --post_content="$content" >/dev/null 2>&1
    echo "  [Page] $title (created)"
  fi
}

create_page "About Us" "<p>We are an independent team that buys, tests, and compares gear so you do not have to guess. Our reviews cover e-bikes, dirt bikes, powersports, generators, outdoor power equipment, and more.</p><p>(Edit this page: add your story, photos, and why readers should trust you. AdSense and readers both reward a real About page.)</p>"

create_page "Contact" "<p>Have a question, a product to suggest, or a correction? Reach us at: <strong>your-email@example.com</strong></p><p>(Replace with a real email and/or add a contact form plugin like WPForms.)</p>"

create_page "Privacy Policy" "<p>This Privacy Policy explains how we collect and use information on this website, including cookies used by Google AdSense and analytics.</p><p><strong>TODO:</strong> Generate a full policy at a free generator (e.g. termsfeed.com) and paste it here. AdSense requires a real Privacy Policy that mentions third-party cookies/DoubleClick.</p>"

create_page "Affiliate Disclaimer" "<p>This site contains affiliate links. If you buy through them, we may earn a commission at no extra cost to you. This never affects our ratings or recommendations.</p><p>As an Amazon Associate we earn from qualifying purchases.</p>"

# ---------------------------------------------------------------------
# 3. CLEANUP DEFAULT JUNK
# ---------------------------------------------------------------------
echo ""
echo ">> Removing default 'Hello World' post and 'Sample Page'..."
wp post delete $(wp post list --post_type=post --field=ID --format=ids 2>/dev/null) --force 2>/dev/null || true
wp post delete $(wp post list --post_type=page --name="sample-page" --field=ID --format=ids 2>/dev/null) --force 2>/dev/null || true

# ---------------------------------------------------------------------
# 4. PERMALINKS (SEO-friendly /post-name/)
# ---------------------------------------------------------------------
echo ""
echo ">> Setting SEO-friendly permalinks..."
wp rewrite structure '/%postname%/' --hard >/dev/null 2>&1
wp rewrite flush --hard >/dev/null 2>&1

# ---------------------------------------------------------------------
# 5. SITE TITLE / TAGLINE
# ---------------------------------------------------------------------
echo ""
echo ">> Setting site title & tagline (edit these later)..."
wp option update blogname "Reviews Hub" >/dev/null 2>&1
wp option update blogdescription "Powerful gear for riders, workers & the outdoors — reviewed & compared." >/dev/null 2>&1

echo ""
echo "=================================================="
echo " DONE! Categories, subcategories, and pages created."
echo " Next: pick a theme (GeneratePress/Kadence) and start writing."
echo "=================================================="
