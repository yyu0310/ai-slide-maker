---
marp: true
theme: default
paginate: true
size: 16:9
header: '{{Talk title}}'
footer: '{{Event name}} {{YYYY/MM/DD}}'
style: |
  section {
    font-family: 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
    font-size: 26px;
    background-color: #fafafa;
    color: #1a1a2e;
  }
  section.lead, section.part {
    text-align: center;
    background: linear-gradient(135deg, #FFCBA4 0%, #F4906A 100%);
    color: #2d1505;
  }
  section.lead h1 {
    font-size: 48px;
    color: #2d1505;
    border-bottom: 3px solid #2d1505;
  }
  section.lead h2, section.part h2 {
    color: #5c2800;
  }
  section.part h1 {
    font-size: 60px;
    color: #2d1505;
    border-bottom: 3px solid #2d1505;
  }
  section.part h2 {
    font-size: 36px;
  }
  section.lead strong, section.part strong, section.lead a {
    color: #2d1505;
  }
  section.part ul {
    text-align: left;
    margin-top: 24px;
    font-size: 26px;
    line-height: 1.8;
  }
  section.top {
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
  }
  section.dense {
    padding: 48px 64px;
    font-size: 22px;
  }
  section.dense h1 {
    font-size: 34px;
    margin-bottom: 0;
  }
  h1 {
    color: #1a1a2e;
    border-bottom: 3px solid #c84b18;
    padding-bottom: 8px;
  }
  h2 {
    color: #16213e;
  }
  strong {
    color: #c84b18;
  }
  blockquote {
    border-left: 4px solid #c84b18;
    background: #f0e9e9;
    padding: 8px 16px;
    color: #1a1a2e;
  }
  table {
    font-size: 24px;
    width: 92%;
    border-collapse: collapse;
    margin: auto;
    display: table;
  }
  table tr {
    background: transparent !important;
  }
  table th {
    background: #2d2420;
    color: #fafafa;
    border: none;
    padding: 16px 20px;
    text-align: left;
  }
  table td {
    border: none;
    border-bottom: 1px solid #e0dbd8;
    padding: 16px 20px;
    text-align: left;
  }
  table tr:last-child td {
    border-bottom: none;
  }
  table.axis {
    width: auto;
  }
  table.axis td {
    border: none;
    padding: 6px 24px;
  }
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 40px;
  }
  .kicker {
    color: #c84b18;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .small {
    font-size: 18px;
  }
  .tag {
    display: inline-block;
    background: #c84b18;
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 18px;
    margin-right: 6px;
  }
  p > img {
    display: block;
    margin: 0 auto;
    width: auto;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _header: '' -->
<!-- _footer: '' -->

# {{Talk title}}

## {{Subtitle}}

**{{Your name}}**
{{Event name}} · {{YYYY/MM/DD}}

<!-- Speaker notes go in comments like this one. The audience never sees them. -->

---

# Agenda

### Part 1｜{{First part}}

### Part 2｜{{Second part}}

### Part 3｜{{Third part}}

---

<!-- _class: part -->
<!-- _paginate: false -->

# Part 1

## {{First part}}

---

# {{One claim, written as a sentence}}

- {{Point}}
- {{Point}}
- {{Point}}

> {{The one line to remember}}

---

# {{Comparison title}}

| {{Item}} | {{Option A}} | {{Option B}} |
|---|---|---|
| {{Row}} | {{Value}} | {{Value}} |
| {{Row}} | {{Value}} | {{Value}} |

---

# {{Text left, image right}}

![bg right:40% contain](./assets/{{p6_topic}}.png)

- {{Point}}
- {{Point}}

---

# {{Two columns}}

<div class="cols">
<div>

**{{Left heading}}**

- {{Point}}
- {{Point}}

</div>
<div>

**{{Right heading}}**

- {{Point}}
- {{Point}}

</div>
</div>

---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _header: '' -->
<!-- _footer: '' -->

# {{Closing line}}

## {{Call to action}}

**{{Your name}}｜{{Contact}}**
