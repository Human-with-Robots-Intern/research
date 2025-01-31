graph [
  directed 1
  node [
    id 0
    label "Prepare Egg for Cooking"
    time 5
  ]
  node [
    id 1
    label "Cook the Egg"
    time 5
  ]
  node [
    id 2
    label "Finish Cooking and Turn Off Stove"
    time 1
  ]
  node [
    id 3
    label "Wash Edible Vegetable"
    time 5
  ]
  node [
    id 4
    label "Wash Lettuce"
    time 5
  ]
  edge [
    source 0
    target 1
    info [
      Type "After"
      Interval 0
      IsCritical 0
    ]
  ]
  edge [
    source 1
    target 2
    info [
      Type "After"
      Interval 5
      IsCritical 1
    ]
  ]
]
