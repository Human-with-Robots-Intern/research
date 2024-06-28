def printing_queue(pq):
    temp_list = []
    while not pq.empty():
        item = pq.get()
        temp_list.append(item)
        print(item)  # Print the item

    # Put elements back into the priority queue
    for item in temp_list:
        pq.put(item)