// SPDX-License-Identifier: MPL-2.0
// The application cards, NBT Manager's release and the "Updated" date, read from
// catalog.json: the file the phone app's Get apps tab reads. Also the hero's screen.
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

  // Only absolute https links (GitHub releases and repositories).
  function safeUrl(url) {
    return typeof url === "string" && /^https:\/\//.test(url) ? url : null;
  }

  // Only a picture in this site: icons/ or screens/.
  function sitePicture(path, folder) {
    return typeof path === "string" && new RegExp(`^${folder}/[\\w-]+\\.(png|svg|webp)$`).test(path) ? path : null;
  }

  function sizeText(size) {
    return size >= 1048576 ? `${(size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;
  }

  function dateText(stamp) {
    const date = new Date(stamp);
    if (!stamp || Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  }

  // The same hue for an app every time: the first four hex digits of SHA-256(id), mod 360.
  async function hue(id) {
    if (!crypto.subtle) return 210;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(id));
    const bytes = new Uint8Array(digest);
    return ((bytes[0] << 8) | bytes[1]) % 360;
  }

  function tile(app, size) {
    const icon = sitePicture(app.icon, "icons");
    const node = el("div", { class: "tile", "aria-hidden": "true" });
    if (icon) {
      node.append(el("img", { src: icon, alt: "", width: String(size), height: String(size) }));
    } else {
      const words = String(app.name).replace(/-/g, " ").split(/\s+/).filter(Boolean);
      node.textContent = words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    }
    return node;
  }

  function link(label, href) {
    const url = safeUrl(href);
    return url ? el("a", { href: url }, label) : null;
  }

  function row(term, value) {
    return value ? el("div", {}, el("dt", {}, term), el("dd", {}, value)) : null;
  }

  // Version, size, date and licence, folded away: the card leads with what the app does.
  function details(app, stable, beta) {
    const newest = stable || beta;
    const file = newest && newest.files && newest.files[0];
    const links = el("p", { class: "more-links" });
    if (stable && stable.files[0]) links.append(link(`Package ${stable.version} (.nbt)`, stable.files[0].url) || "");
    if (beta && beta.files[0]) links.append(link(`Beta ${beta.version} (.nbt)`, beta.files[0].url) || "");
    links.append(link("Source", `https://github.com/${app.repo}`) || "");
    return el("details", { class: "more" },
      el("summary", {}, newest ? `Version ${newest.version}` : "Details"),
      el("dl", {},
        file ? row("Size", sizeText(file.size)) : null,
        newest ? row("Released", dateText(newest.date)) : null,
        row("Licence", app.license)),
      links);
  }

  async function card(app, featured) {
    const releases = Array.isArray(app.releases) ? app.releases : [];
    const stable = releases.find((r) => !r.prerelease);
    const beta = releases.find((r) => r.prerelease);
    const title = typeof app.title === "string" && app.title ? app.title : String(app.name);

    const kind = el("p", { class: "kind" });
    const category = CATEGORIES[app.category] || String(app.category || "");
    kind.append(title === app.name ? category : `${app.name} · ${category}`);
    if (!releases.length) kind.append(" ", el("span", { class: "chip soon" }, "Coming soon"));
    else if (!stable) kind.append(" ", el("span", { class: "chip beta" }, "Beta"));

    const node = el("article", { class: featured ? "card featured-card" : "card", id: `app-${app.id}` });
    node.style.setProperty("--hue", String(await hue(app.id)));
    if (featured) {
      const cover = sitePicture(app.cover, "screens");
      node.append(el("div", { class: cover ? "cover" : "cover plain", "aria-hidden": "true" },
        cover ? el("img", { src: cover, alt: "", width: "1280", height: "480", loading: "lazy" }) : tile(app, 72)));
    }
    node.append(el("div", { class: "card-body" },
      el("div", { class: "card-head" }, tile(app, 48), el("div", {}, el("h3", {}, title), kind)),
      el("p", { class: "summary" }, app.summary),
      details(app, stable, beta)));
    return node;
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
    // The featured ones first, in the catalog's order; the others by name, A to Z.
    const featured = apps.filter((a) => a.featured === true);
    const others = apps.filter((a) => a.featured !== true);
    others.sort((a, b) => String(a.name).localeCompare(String(b.name), "en", { sensitivity: "base", numeric: true }));
    const shelf = document.getElementById("app-featured");
    if (shelf) shelf.replaceChildren(...(await Promise.all(featured.map((a) => card(a, true)))));
    grid.replaceChildren(...(await Promise.all((shelf ? others : apps).map((a) => card(a, false)))));
    grid.removeAttribute("aria-busy");
    const head = document.getElementById("app-more-head");
    if (head) head.hidden = !(shelf && featured.length && others.length);

    const manager = managerLine(catalog.apps.find((a) => a && a.id === "manager"));
    const slot = document.getElementById("manager-release");
    if (slot && manager) slot.replaceChildren(manager);
    const generated = document.getElementById("catalog-generated");
    if (generated) generated.textContent = dateText(catalog.generated);
  }

  // A set of slides (the hero's screen, the themes): one at a time, changed by its buttons
  // or every `data-slides` milliseconds.
  function wireDisplay(display) {
    const slides = [...display.querySelectorAll(".slide")];
    const buttons = [...display.querySelectorAll("[data-show]")];
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let timer = 0;
    const show = (name) => {
      for (const slide of slides) {
        const on = slide.dataset.slide === name;
        slide.classList.toggle("is-on", on);
        const image = slide.querySelector("img[data-src]");
        // The animated capture is fetched when its slide first shows.
        if (on && image && !still) {
          image.src = image.dataset.src;
          image.removeAttribute("data-src");
        }
      }
      for (const button of buttons) {
        const on = button.dataset.show === name;
        button.classList.toggle("is-on", on);
        button.setAttribute("aria-pressed", String(on));
      }
    };
    const next = () => {
      const at = slides.findIndex((s) => s.classList.contains("is-on"));
      show(slides[(at + 1) % slides.length].dataset.slide);
    };
    for (const button of buttons) {
      button.addEventListener("click", () => {
        clearInterval(timer);
        show(button.dataset.show);
      });
    }
    if (!still && slides.length > 1) timer = setInterval(next, Number(display.dataset.slides) || 9000);
  }

  function start() {
    document.querySelectorAll("[data-slides]").forEach(wireDisplay);
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
