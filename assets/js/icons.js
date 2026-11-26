/* Inline SVG sprite (no network, no icon font). Usage: JB.ic('wave') */
(function(){
const P={
wave:'<path d="M2 15c2.5-3.5 4.5-3.5 7 0s4.5 3.5 7 0 4.5-3.5 6-1"/><path d="M2 10c2.5-3.5 4.5-3.5 7 0s4.5 3.5 7 0 4.5-3.5 6-1"/>',
wind:'<path d="M3 8h10a3 3 0 1 0-3-3"/><path d="M3 12h14a3 3 0 1 1-3 3"/><path d="M3 16h6"/>',
eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
bolt:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
check:'<path d="M5 13l4 4L19 7"/>',
warn:'<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
stop:'<circle cx="12" cy="12" r="9"/><path d="M8 8l8 8M16 8l-8 8"/>',
ban:'<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
q:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.1 1-1.1 1.8M12 17v.5"/>',
info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
speaker:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
share:'<path d="M12 3v12M7 8l5-5 5 5M5 13v7h14v-7"/>',
port:'<circle cx="12" cy="5" r="2"/><path d="M12 7v14M6 12H4a8 8 0 0 0 16 0h-2M8 11h8"/>',
arrow:'<path d="M12 3l6 9h-4v9h-4v-9H6z"/>',
cal:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
map:'<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
refresh:'<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
dl:'<path d="M12 3v12M7 11l5 5 5-5M5 20h14"/>',
shield:'<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
fish:'<path d="M2 12c3-5 9-7 14-3l5-3v12l-5-3c-5 4-11 2-14-3z"/><circle cx="7" cy="11" r=".8"/>',
globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
sms:'<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
/* boats (filled) */
b_small:'<path d="M3 15h18l-3 4H7z"/><path d="M11 14V5l6 9z"/>',
b_mech:'<path d="M2 16h19l-3 4H6z"/><path d="M6 15v-4h7l2 4zM9 11V8h3v3"/><path d="M1 13l2 3"/>',
b_trawl:'<path d="M2 17h20l-3 4H6z"/><path d="M5 16v-5h8v5zM8 11V6h3v5zM14 16l5-9M19 7v10"/>'
};
const FILLED={b_small:1,b_mech:1,b_trawl:1};
window.JBI=function(name,cls){return '<svg class="ic'+(FILLED[name]?' fill':'')+(cls?' '+cls:'')+'" viewBox="0 0 24 24" aria-hidden="true">'+(P[name]||'')+'</svg>'};
})();
