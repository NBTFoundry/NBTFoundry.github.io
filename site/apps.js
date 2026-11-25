// SPDX-License-Identifier: MPL-2.0
// The application cards, NBT Manager's release and the "Updated" date, read from
// catalog.json: the file the phone app's Get apps tab reads.
"use strict";

(() => {
  const CATEGORIES = { system: "System", game: "Game", emulator: "Emulator", tool: "Tool" };

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (name === "class") node.className = value;
      else node.setAttribute(name, value);
    }
    for (const child of children) {
      if (child != null) node.append(child);
    }
    return node;
  }

  // Only absolute https links (GitHub releases and repositories) or an icon in this site.
  function safeUrl(url) {
    return typeof url === "string" && /^https:\/\//.test(url) ? url : null;
  }

  function sizeText(size) {
    return size >= 1048576 ? `${(size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;
  }

  function dateText(stamp) {
    const date = new Date(stamp);
    if (!stamp || Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  }

  // The same hue for an app as before: the first four hex digits of SHA-256(id), mod 360.
  async function hue(id) {
    if (!crypto.subtle) return 210;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(id));
    const bytes = new Uint8Array(digest);
    return ((bytes[0] << 8) | bytes[1]) % 360;
  }

  async function tile(app) {
    const node = el("div", { class: "tile", "aria-hidden": "true" });
    node.style.setProperty("--hue", String(await hue(app.id)));
    if (typeof app.icon === "string" && /^icons\/[\w.-]+\.png$/.test(app.icon)) {
      node.append(el("img", { src: app.icon, alt: "", width: "56", height: "56" }));
    } else {
      const words = String(app.name).replace(/-/g, " ").split(/\s+/).filter(Boolean);
      node.textContent = words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    }
    return node;
  }

  function button(label, href, primary) {
    const url = safeUrl(href);
    return url ? el("a", { class: primary ? "button small primary" : "button small", href: url }, label) : null;
  }

  async function card(app) {
    const releases = Array.isArray(app.releases) ? app.releases : [];
    const stable = releases.find((r) => !r.prerelease);
    const beta = releases.find((r) => r.prerelease);
    const newest = releases[0];

    const chips = el("div", { class: "chips" },
      el("span", { class: "chip" }, CATEGORIES[app.category] || String(app.category || "")));
    if (!releases.length) chips.append(el("span", { class: "chip soon" }, "Coming soon"));
    else if (!stable) chips.append(el("span", { class: "chip beta" }, "Beta"));

    const meta = el("div", { class: "meta" });
    if (newest && newest.files && newest.files[0]) {
      meta.append(el("span", {}, el("b", {}, newest.version),
        ` · ${sizeText(newest.files[0].size)} · ${dateText(newest.date)}`));
    }
    meta.append(el("span", {}, "Licence ", el("b", {}, app.license)));

    const actions = el("div", { class: "actions" });
    if (stable) actions.append(button(`Download ${stable.version}`, stable.files[0].url, true) || "");
    if (beta) actions.append(button(`Beta ${beta.version}`, beta.files[0].url, !stable) || "");
    actions.append(button("Source", `https://github.com/${app.repo}`, false) || "");

    return el("article", { class: "card", id: `app-${app.id}` },
      el("div", { class: "card-head" }, await tile(app), el("div", {}, el("h3", {}, app.name), chips)),
      el("p", { class: "summary" }, app.summary),
      meta,
      actions);
  }

  function managerLine(app) {
    if (!app || !app.releases || !app.releases.length) return null;
    const release = app.releases[0];
    const label = el("span", {}, "NBT Manager ", el("b", {}, release.version));
    if (release.prerelease) label.append(" ", el("span", { class: "chip beta" }, "Beta"));
    const notes = safeUrl(release.page);
    return el("div", { class: "release" }, label, notes ? el("a", { href: notes }, "Release notes") : null);
  }

  function failed(grid) {
    grid.replaceChildren(el("p", { class: "note" }, "The list could not be loaded. See ",
      el("a", { href: "catalog.json" }, "catalog.json"), " or ",
      el("a", { href: "https://github.com/NBTFoundry" }, "NBTFoundry on GitHub"), "."));
    grid.removeAttribute("aria-busy");
  }

  // The arrows beside the heading: shown while the shelf is wider than the page, off at either end.
  function wireShelf(shelf) {
    const nav = document.querySelector(".shelf-nav");
    if (!nav) return;
    const [back, next] = nav.querySelectorAll("button");
    const update = () => {
      const room = shelf.scrollWidth - shelf.clientWidth;
      nav.hidden = room <= 1;
      back.disabled = shelf.scrollLeft <= 1;
      next.disabled = shelf.scrollLeft >= room - 1;
    };
    for (const button of [back, next]) {
      button.addEventListener("click", () => {
        shelf.scrollBy({ left: Number(button.dataset.step) * shelf.clientWidth * 0.9 });
      });
    }
    shelf.addEventListener("scroll", update, { passive: true });
    new ResizeObserver(update).observe(shelf);
    update();
  }

  async function load() {
    const grid = document.getElementById("app-grid");
    if (!grid) return;
    let catalog;
    try {
      // Pages lets browsers keep the file 10 minutes: an unused query and no-store skip every cache.
      const response = await fetch(`catalog.json?t=${Date.now()}`, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      catalog = await response.json();
      if (!catalog || !Array.isArray(catalog.apps)) throw new Error("no apps");
    } catch (error) {
      console.error("catalog.json:", error);
      failed(grid);
      return;
    }
    const apps = catalog.apps.filter((a) => a && a.id !== "manager");
    // By name, A to Z.
    apps.sort((a, b) => String(a.name).localeCompare(String(b.name), "en", { sensitivity: "base", numeric: true }));
    grid.replaceChildren(...(await Promise.all(apps.map(card))));
    grid.removeAttribute("aria-busy");
    wireShelf(grid);

    const manager = managerLine(catalog.apps.find((a) => a && a.id === "manager"));
    const slot = document.getElementById("manager-release");
    if (slot && manager) slot.replaceChildren(manager);
    const generated = document.getElementById("catalog-generated");
    if (generated) generated.textContent = dateText(catalog.generated);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
})();
