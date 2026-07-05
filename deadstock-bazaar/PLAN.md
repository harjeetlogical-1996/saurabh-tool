# DeadStock Bazaar — Project Plan

> Local shops ka slow-moving / dead stock clearance platform.
> Dukaandaar apna na-bikne wala maal sasti clearance price pe list kare, aas-paas ke buyers dhoondh ke khareedein.
> Stack: **Next.js 14 (App Router) + Tailwind**. Backend baad mein decide.

---

## 1. Problem & Solution

**Problem:**
- Chhoti dukaanon ke paas purana / slow-moving stock pada rehta hai — paisa block, jagah block.
- Customers ko pata nahi chalta kahaan sasta clearance maal milta hai.
- Dukaandaar ke paas online bechne ka asaan tareeka nahi (Amazon/Flipkart bohot complex + commission heavy).

**Solution:**
- Ek simple local platform: dukaandaar 2 minute mein dead stock list kare (photo + MRP + clearance price).
- Buyer apne area / pincode ka sasta clearance maal browse kare.
- Jitna zyada discount, listing utni upar (urgency-driven).
- Deal WhatsApp / in-shop pickup pe close ho (online payment ka jhanjhat MVP mein nahi).

---

## 2. Target Users

| User | Goal |
|---|---|
| **Dukaandaar (Seller)** | Dead stock se jaldi paisa nikalna, jagah khaali karna |
| **Local Buyer** | Aas-paas sasta / clearance maal dhoondhna |
| **Bargain hunters** | Discount deals track karna |

---

## 3. Core Features

### 3.1 MVP (Phase 1)
- [ ] Shop registration / login
- [ ] Add dead-stock listing (photo, item name, category, MRP, clearance price, qty, optional expiry)
- [ ] Auto discount % calculation + badge ("60% OFF", "Clearance", "Last 3 left")
- [ ] Browse / search page (category + area filter)
- [ ] Sort: highest discount first, newest, price low-high
- [ ] Listing detail page
- [ ] Contact shop (WhatsApp deep-link / phone) ya "Reserve" button
- [ ] Pincode / area based filtering

### 3.2 Phase 2 (Growth)
- [ ] Featured / boosted listings (paid)
- [ ] Shop public profile page (saari listings)
- [ ] Buyer accounts + wishlist / save
- [ ] Expiry auto-delist (date nikal gayi → hide)
- [ ] Email/WhatsApp alerts ("aapke area mein naya clearance")
- [ ] Basic shop analytics (views, contacts)

### 3.3 Phase 3 (Monetize / scale)
- [ ] Online reserve + token payment
- [ ] Commission on sales
- [ ] AdSense on browse pages
- [ ] Multi-city expansion
- [ ] Ratings / reviews for shops

---

## 4. Monetization
1. **Featured listings** — dukaandaar paisa de ke top pe aaye.
2. **Premium shop** — unlimited listings + analytics + verified badge.
3. **Commission** — Phase 3, successful clearance pe %.
4. **AdSense** — browse/category pages pe (familiar model).

---

## 5. Data Model (draft)

### `Shop`
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| name | string | dukaan ka naam |
| ownerName | string | |
| phone | string | WhatsApp ke liye |
| area | string | locality |
| city | string | |
| pincode | string | filter ke liye |
| category | string | primary category |
| isVerified | bool | premium/verified |
| createdAt | datetime | |

### `Listing`
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| shopId | uuid | FK → Shop |
| title | string | item naam |
| description | text | optional |
| category | string | |
| imageUrl | string | photo |
| mrp | number | original price |
| clearancePrice | number | discounted |
| discountPct | number | computed = (mrp-clearance)/mrp*100 |
| quantity | int | stock left |
| expiryDate | date | optional |
| status | enum | active / sold / expired |
| isFeatured | bool | paid boost |
| views | int | |
| createdAt | datetime | |

### Categories (initial)
Kapde · Footwear · Electronics · Grocery/FMCG · Stationery · Home & Kitchen · Toys · Cosmetics · Books · Hardware

---

## 6. Pages / Routes (Next.js App Router)

| Route | Page | Notes |
|---|---|---|
| `/` | Home | hero + top discounts + category tiles + area picker |
| `/browse` | Browse | filter (category, area, discount), sort, grid |
| `/listing/[id]` | Listing detail | photo, price, discount, contact/reserve |
| `/shop/[id]` | Shop profile | saari listings (Phase 2) |
| `/sell` | Add listing | form (auth required) |
| `/dashboard` | Shop dashboard | meri listings, edit/delete, stats |
| `/login`, `/signup` | Auth | shop accounts |

---

## 7. Tech Stack
- **Framework:** Next.js 14 (App Router), TypeScript
- **Styling:** Tailwind CSS
- **State/Data:** Server Components + (later) DB
- **DB (later):** Supabase (Postgres + auth + image storage) — recommended
- **Images:** Supabase Storage / Cloudinary
- **Deploy:** Vercel (free)

---

## 8. Build Order (proposed)
1. **Plan review** ← abhi yahaan
2. Next.js + Tailwind scaffold
3. Frontend with dummy JSON data: Home → Browse → Listing detail
4. Add listing form (UI only)
5. Backend (Supabase): schema + auth + real data
6. Wire forms → DB, image upload
7. Featured listings + dashboard
8. Polish, deploy

---

## 9. Open Questions
- [ ] App ka naam final? (DeadStock Bazaar / ClearKaro / SastaStock ...)
- [ ] City-specific launch ya all-India?
- [ ] Buyer login zaroori ya guest browse + direct WhatsApp?
- [ ] Language: English / Hindi / Hinglish UI?
- [ ] Online payment chahiye ya sirf contact-and-pickup (MVP)?
