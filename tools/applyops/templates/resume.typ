// ATS-friendly resume template
// Input: JSON data via data.json in working directory

#let data = json("data.json")

#set document(title: data.name + " — Resume")
#set page(margin: (x: 0.4in, y: 0.3in), paper: "us-letter")
#set text(font: "New Computer Modern", size: 9pt)
#set par(justify: false, leading: 0.45em)
#set list(indent: 0.1in, body-indent: 0.08in, spacing: 0.25em, marker: [•])

#set page(numbering: none)
#show link: set text(fill: rgb("#0645AD"))

// --- Helper: render contact item as link if it looks like a URL ---
#let render-contact(item) = {
  if item.starts-with("github.com") or item.starts-with("linkedin.com") {
    link("https://" + item)[#item]
  } else if item.starts-with("http") {
    link(item)[#item]
  } else if item.contains("@") {
    link("mailto:" + item)[#item]
  } else {
    item
  }
}

// --- Header ---
#align(center)[
  #text(size: 16pt, weight: "bold")[#data.name]
  #v(1.5pt)
  #text(size: 8.5pt)[
    #data.contact.items.map(render-contact).join("  |  ")
  ]
]

#v(2pt)

// --- Helper functions ---
#let section(title, body) = {
  v(4pt)
  text(size: 9.5pt, weight: "bold")[#upper(title)]
  v(-3pt)
  line(length: 100%, stroke: 0.5pt)
  v(1pt)
  body
}

#let entry(title: "", org: "", location: "", dates: "", details: ()) = {
  v(3pt)
  grid(
    columns: (1fr, auto),
    [#text(weight: "bold")[#title]#if org != "" [, #org#if location != "" [, #location]]],
    align(right)[#emph[#dates]],
  )
  if details.len() > 0 {
    v(1pt)
    for detail in details {
      [- #detail]
    }
  }
}

// --- Summary / Objective ---
#if "summary" in data and data.summary != "" {
  section("Summary")[
    #data.summary
  ]
}

// --- Experience ---
#if "experience" in data and data.experience.len() > 0 {
  section("Experience")[
    #for job in data.experience {
      entry(
        title: job.title,
        org: job.at("company", default: ""),
        location: job.at("location", default: ""),
        dates: job.at("dates", default: ""),
        details: job.at("details", default: ()),
      )
    }
  ]
}

// --- Education ---
#if "education" in data and data.education.len() > 0 {
  section("Education")[
    #for edu in data.education {
      v(3pt)
      grid(
        columns: (1fr, auto),
        [#text(weight: "bold")[#edu.at("degree", default: "")], #edu.at("school", default: "")#if edu.at("details", default: ()).len() > 0 [ — #edu.at("details", default: ()).join(", ")]],
        align(right)[#emph[#edu.at("dates", default: "")]],
      )
    }
  ]
}

// --- Skills ---
#if "skills" in data and data.skills.len() > 0 {
  section("Skills")[
    #table(
      columns: (auto, 1fr),
      stroke: none,
      inset: (x: 0pt, y: 1.5pt),
      column-gutter: 1.5em,
      ..for skill in data.skills {
        (text(weight: "bold")[#skill.category], skill.items.join(", "))
      }
    )
  ]
}

// --- Projects ---
#if "projects" in data and data.projects.len() > 0 {
  section("Projects")[
    #for proj in data.projects {
      entry(
        title: proj.at("name", default: ""),
        org: proj.at("tech", default: ""),
        dates: proj.at("dates", default: ""),
        details: proj.at("details", default: ()),
      )
    }
  ]
}

// --- Publications ---
#if "publications" in data and data.publications.len() > 0 {
  section("Publications")[
    #for pub in data.publications {
      [- *#pub.title* — #pub.venue #if "year" in pub [(#pub.year)]]
    }
  ]
}
