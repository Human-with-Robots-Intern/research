graph [
  directed 1
  node [
    id 0
    label "Wash Plate_part_1"
    time 4
  ]
  node [
    id 1
    label "Wash Plate_part_2"
    time 4
  ]
  node [
    id 2
    label "Wash Egg"
    time 2
  ]
  node [
    id 3
    label "Wash Potato"
    time 2
  ]
  node [
    id 4
    label "Prepare Egg Fry"
    time 10
  ]
  node [
    id 5
    label "Turn off stove after cooking"
    time 0
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
    source 2
    target 4
    info [
      Type "After"
      Interval 5
      IsCritical 1
    ]
  ]
  edge [
    source 4
    target 5
    info [
      Type "After"
      Interval 10
      IsCritical 1
    ]
  ]
]
