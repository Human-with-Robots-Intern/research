graph [
  directed 1
  node [
    id 0
    label "Wash Egg"
    time 5
  ]
  node [
    id 1
    label "Wash Potato"
    time 5
  ]
  node [
    id 2
    label "Wash Tomato"
    time 5
  ]
  node [
    id 3
    label "Prepare and Cook Fried Egg"
    time 10
  ]
  node [
    id 4
    label "Turn off stove after cooking"
    time 0
  ]
  edge [
    source 0
    target 3
    info [
      Type "After"
      Interval 0
      IsCritical 0
    ]
  ]
  edge [
    source 3
    target 4
    info [
      Type "After"
      Interval 10
      IsCritical 1
    ]
  ]
]
