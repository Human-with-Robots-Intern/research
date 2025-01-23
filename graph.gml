graph [
  directed 1
  node [
    id 0
    label "Retrieve Tomato"
    time 0.1
  ]
  node [
    id 1
    label "Retrieve Egg"
    time 0.1
  ]
  node [
    id 2
    label "Retrieve Lettuce"
    time 0.1
  ]
  node [
    id 3
    label "Boil Water"
    time 0.1
  ]
  node [
    id 4
    label "Cook Pasta"
    time 0.1
  ]
  node [
    id 5
    label "Saut&#233; Ingredients"
    time 0.1
  ]
  node [
    id 6
    label "Add Seasoning"
    time 0.1
  ]
  node [
    id 7
    label "Simmer Mixture"
    time 0.1
  ]
  node [
    id 8
    label "Turn Off Stove"
    time 0.1
  ]
  edge [
    source 0
    target 1
    info [
      Type "After"
      Interval 2
      Urgency 0
    ]
  ]
  edge [
    source 0
    target 5
    info [
      Type "After"
      Interval 2
      Urgency 0
    ]
  ]
  edge [
    source 3
    target 4
    info [
      Type "After"
      Interval 3
      Urgency 1
    ]
  ]
  edge [
    source 6
    target 7
    info [
      Type "After"
      Interval 1
      Urgency 1
    ]
  ]
  edge [
    source 7
    target 8
    info [
      Type "After"
      Interval 10
      Urgency 1
    ]
  ]
]
