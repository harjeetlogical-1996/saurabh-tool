#!/usr/bin/env bash
# =====================================================================
#  Manual WordPress install + full setup for Local site "reviewshub"
#  Runs everything: extract WP -> wp-config -> install -> categories
#  -> subcategories -> 4 AdSense pages -> permalinks -> cleanup.
# =====================================================================
set -e

PUBLIC="/c/Users/Admin/Local Sites/reviewshub/app/public"
ZIP="/tmp/wp-latest.zip"
PHP="/c/Users/Admin/AppData/Roaming/Local/lightning-services/php-8.2.29+0/bin/win64/php.exe"
WPCLI="/c/Program Files (x86)/Local/resources/extraResources/bin/wp-cli/wp-cli.phar"

# DB + site details (from Local sites.json)
DB_NAME="local"; DB_USER="root"; DB_PASS="root"; DB_HOST="127.0.0.1:10012"
SITE_URL="http://reviewshub.local:10010"
SITE_TITLE="Reviews Hub"
ADMIN_USER="admin"; ADMIN_PASS="admin123"; ADMIN_EMAIL="admin@reviewshub.local"

# wp() helper — runs wp-cli with Local's PHP against the site
wp () { "$PHP" "$WPCLI" --path="$PUBLIC" "$@"; }

echo "==== 1. Extracting WordPress into app/public ===="
cd /tmp
rm -rf /tmp/wordpress
unzip -q "$ZIP" -d /tmp/
# move contents of wordpress/ into public/
cp -r /tmp/wordpress/. "$PUBLIC/"
echo "   WP files copied ✅"

echo "==== 2. Creating wp-config.php ===="
wp config create --dbname="$DB_NAME" --dbuser="$DB_USER" --dbpass="$DB_PASS" \
  --dbhost="$DB_HOST" --force --skip-check
echo "   wp-config.php created ✅"

echo "==== 3. Resetting database (clean install) ===="
wp db reset --yes || echo "   (db reset skipped)"

echo "==== 4. Installing WordPress ===="
wp core install --url="$SITE_URL" --title="$SITE_TITLE" \
  --admin_user="$ADMIN_USER" --admin_password="$ADMIN_PASS" --admin_email="$ADMIN_EMAIL" \
  --skip-email
echo "   WordPress installed ✅  (login: $ADMIN_USER / $ADMIN_PASS)"

echo "==== 5. Categories + subcategories ===="
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
for entry in "${CATEGORIES[@]}"; do
  parent="${entry%%|*}"; subs="${entry#*|}"
  parent_id=$(wp term create category "$parent" --porcelain 2>/dev/null \
              || wp term list category --name="$parent" --field=term_id --format=ids 2>/dev/null)
  echo "  [Category] $parent (id: $parent_id)"
  IFS=',' read -ra SUBARR <<< "$subs"
  for sub in "${SUBARR[@]}"; do
    wp term create category "$sub" --parent="$parent_id" >/dev/null 2>&1 \
      && echo "      - $sub" || echo "      - $sub (skip)"
  done
done

echo "==== 6. AdSense pages ===="
mk_page () {
  wp post create --post_type=page --post_status=publish --post_title="$1" --post_content="$2" >/dev/null 2>&1 \
    && echo "  [Page] $1 ✅"
}
mk_page "About Us" "<p>We are an independent team that researches, compares, and ranks the best websites to buy gear online — e-bikes, dirt bikes, powersports, generators, outdoor power equipment, and more. Our goal: help you find the most trusted store with the best price, shipping, and selection.</p><p>(Edit: add your story and photos.)</p>"
mk_page "Contact" "<p>Questions, suggestions, or corrections? Email us: <strong>your-email@example.com</strong></p><p>(Replace with a real email / add a contact form.)</p>"
mk_page "Privacy Policy" "<p>This Privacy Policy explains how we handle data and cookies, including those used by Google AdSense and analytics. <strong>TODO:</strong> paste a full generated policy (termsfeed.com) — AdSense requires this.</p>"
mk_page "Affiliate Disclaimer" "<p>Some links on this site may be affiliate links. If you buy through them we may earn a commission at no extra cost to you. This never affects our rankings.</p>"

echo "==== 7. Permalinks + cleanup + title ===="
wp rewrite structure '/%postname%/' --hard >/dev/null 2>&1
wp rewrite flush --hard >/dev/null 2>&1
wp post delete $(wp post list --post_type=post --field=ID --format=ids 2>/dev/null) --force >/dev/null 2>&1 || true
wp post delete $(wp post list --post_type=page --name=sample-page --field=ID --format=ids 2>/dev/null) --force >/dev/null 2>&1 || true
wp option update blogdescription "Best websites to buy gear online — compared & ranked." >/dev/null 2>&1

echo ""
echo "=================================================="
echo " ✅ DONE! reviewshub fully set up."
echo "    Site:  $SITE_URL"
echo "    Admin: $SITE_URL/wp-admin  ($ADMIN_USER / $ADMIN_PASS)"
echo "=================================================="
