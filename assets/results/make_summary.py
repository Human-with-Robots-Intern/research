def select_folder():
    # Select a folder
    folder_path = input("Enter the folder path: ")
    return folder_path

def make_summary(folder_path):
    # Make a summary
    json_data =      {
        "approachComparisons" : [
            {
                "approachName": f"{filename}",
                "simulationMakespan": {simulationMakespan},
                "realWorldMakespan": None,
                "computationTime" : {computationTime},
                "actionSuccessRate": {success_rate},
                "timingSuccessRate" : None
            }
        ],
    }
        
def main():
    folder_path = select_folder()
    make_summary(folder_path)

if __name__ == "__main__":
    main()