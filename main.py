from processor import process_all_files
import os



os.environ["TOKENIZERS_PARALLELISM"] = "false"

if __name__ == "__main__":
    print("\n🚀 Starting Generic Log Anomaly Detection Pipeline...\n")
    process_all_files()
    print("\n✅ All files processed. Results saved in 'results/' folder.\n")
