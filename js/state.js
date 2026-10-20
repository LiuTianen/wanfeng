// ── 晚风 · 全局状态 ──

let notes = [];
let editId = null;
let apiKey = null;
let activeGroup = '';
let groups = [];
let allTags = [];
let activeTag = '';
let showCalendar = false;
let calYear, calMonth, calSelectedDate;
let currentView = 'my';
let currentKeyIsAdmin = false;
let connState = 'local';        // local | online | offline | unauth | pending

const listEl = document.getElementById('list');
const searchEl = document.getElementById('search');
const searchWrap = document.querySelector('.search-wrap');
const discoverView = document.getElementById('discover-view');
const discoverList = document.getElementById('discover-list');
const discoverFooter = document.getElementById('discover-footer');
const headerBtns = document.getElementById('header-btns');
const countEl = document.getElementById('count');
const calView = document.getElementById('calendar-view');
