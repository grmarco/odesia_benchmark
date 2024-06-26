import pathlib as pl
import pandas as pd
import argparse


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--train_file_path', type=str, help='Path to the training file')
    parser.add_argument('-d', '--dev_file_path', type=str, help='Path to the dev file')
    parser.add_argument('-s', '--test_file_path', type=str, help='Path to the test file')
    parser.add_argument('-g', '--gold_folder', type=str, help='Path to the gold folder')
    parser.add_argument('-o', '--output_folder', type=str, help='Path to the output folder')

    return parser.parse_args()

def load_split_data(train_file_path, dev_file_path, test_file_path):
    return {'train': pd.read_json(train_file_path, orient='index'), 
            'dev': pd.read_json(dev_file_path, orient='index'), 
            'test': pd.read_json(test_file_path, orient='index')}

def load_gold_data(gold_folder):
    """
    Load gold data from the specified folder.

    Parameters:
    gold_folder (str): The path to the folder containing the gold data files.

    Returns:
    dict: A dictionary containing the loaded gold data.
          The keys of the dictionary are the task numbers (1, 2, 3).
          The values are nested dictionaries, where the keys are the gold types ('hard', 'soft')
          and the values are pandas DataFrames containing the gold data.
    """
    gold_data = {}
    for task in range(1, 4):
        gold_data[task] = {}
        for gold_type in ['hard', 'soft']:
            train_gold_file_path = pl.Path(gold_folder) / f'EXIST2023_training_task{task}_gold_{gold_type}.json'
            dev_gold_file_path = pl.Path(gold_folder) / f'EXIST2023_dev_task{task}_gold_{gold_type}.json'
            test_gold_file_path = pl.Path(gold_folder) / f'EXIST2023_test_task{task}_gold_{gold_type}.json'
            gold_df = pd.concat([pd.read_json(train_gold_file_path, orient='index'), 
                                 pd.read_json(dev_gold_file_path, orient='index'), 
                                 pd.read_json(test_gold_file_path, orient='index')])
            gold_data[task][gold_type] = gold_df
    return gold_data

def join_gold_data_to_split_data(split_data, gold_data):
    """
    Joins gold data to split data.

    Args:
        split_data (dict): A dictionary containing split data.
        gold_data (dict): A dictionary containing gold data.

    Returns:
        dict: A dictionary containing the joined split data.

    """
    for task in range(1, 4):
        for gold_type in ['hard', 'soft']:
            for split, data in split_data.items():
                prefix = f'task{task}_'
                new_df = gold_data[task][gold_type].add_prefix(prefix)
                overlap = set(data.columns) & set(new_df.columns)
                if overlap:
                    data = data.join(new_df, lsuffix='_left', rsuffix='_right')
                else:
                    data = data.join(new_df)
                split_data[split] = data
    return split_data

def save_data_to_json(split_data, output_folder):
    """
    Save split data to JSON files.

    Args:
        split_data (dict): A dictionary containing the split data.
        output_folder (str): The path to the output folder.

    Returns:
        None
    """
    for task in range(1, 4):
        for training_mode in ['hard', 'soft']:
            for eval_mode in ['hard', 'soft']:
                # Skipping the cases where training_mode and eval_mode are incompatible
                if training_mode == 'soft' and eval_mode == 'hard':
                    continue
                task_output_folder = pl.Path(output_folder, f'exist_2023_t{task}_{training_mode}_{eval_mode}')
                task_output_folder.mkdir(parents=True, exist_ok=True)    
                for split, data in split_data.items():
                        for lang in ['en', 'es']:
                            lang_data = data[data['lang'] == lang]
                            task_columns = [col for col in lang_data.columns if f'task{task}_' in col] + ['id_EXIST', 'tweet']
                            task_data = lang_data[task_columns]
                            task_data = task_data.rename(columns={col: col.replace(f'task{task}_', '') for col in task_columns})
                            task_data = task_data.rename(columns={'id_EXIST': 'id', 'tweet': 'text'})
                            if training_mode == 'hard':
                                if eval_mode == 'hard':
                                    task_data = task_data.drop(columns=['soft_label'])
                                else:
                                    # Convert keys in soft label from YES/NO to 0/1
                                    if task == 1:
                                        soft_label_mapping = {'YES': 'sexist', 'NO': 'non-sexist'}
                                        task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                    elif task == 2:
                                        soft_label_mapping = {'DIRECT': 'direct', 'REPORTED': 'reported', 'JUDGEMENTAL': 'judgemental', 'NO': 'non-sexist'}
                                        task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                    elif task == 3:
                                        soft_label_mapping = {'SEXUAL-VIOLENCE': 'sexual-violence',
                                                            'STEREOTYPING-DOMINANCE': 'stereotyping-dominance',
                                                            'NO': 'non-sexist',
                                                            'MISOGYNY-NON-SEXUAL-VIOLENCE': 'misogyny-non-sexual-violence',
                                                            'IDEOLOGICAL-INEQUALITY': 'ideological-inequality',
                                                            'OBJECTIFICATION': 'objectification'}
                                        task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                # Drop null values
                                task_data = task_data.dropna(subset=['hard_label'])
                                if task == 1:    
                                    # Convert hard_label from YES/NO to 0/1
                                    task_data['hard_label'] = task_data['hard_label'].map({'YES': 1, 'NO': 0})
                                    # Cast hard_label to int
                                    task_data['hard_label'] = task_data['hard_label'].astype(int)
                                    task_data['hard_label_text'] = task_data['hard_label'].map({1: 'sexist', 0: 'non-sexist'})
                                    # Rename hard_label to label
                                    task_data = task_data.rename(columns={'hard_label': 'label'})
                                    # Rename hard_label_text to label_text
                                    task_data = task_data.rename(columns={'hard_label_text': 'label_text'})    
                                elif task == 2:
                                    # Convert hard_label from to 0/1
                                    task_data['hard_label'] = task_data['hard_label'].map({'DIRECT': 3, 
                                                                                        'REPORTED': 2, 
                                                                                        'JUDGEMENTAL': 1, 
                                                                                        'NO': 0})
                                    # Cast hard_label to int
                                    task_data['hard_label'] = task_data['hard_label'].astype(int)
                                    task_data['hard_label_text'] = task_data['hard_label'].map({3: 'direct',
                                                                                                2: 'reported',
                                                                                                1: 'judgemental',
                                                                                                0: 'non-sexist'})
                                    # Rename hard_label to label
                                    task_data = task_data.rename(columns={'hard_label': 'label'})
                                    # Rename hard_label_text to label_text
                                    task_data = task_data.rename(columns={'hard_label_text': 'label_text'})
                                elif task == 3:
                                    # Convert hard_label list to numbers
                                    mapping = {'SEXUAL-VIOLENCE': 0,
                                                'STEREOTYPING-DOMINANCE': 1, 
                                                'NO': 2,
                                                'MISOGYNY-NON-SEXUAL-VIOLENCE': 3,      
                                                'IDEOLOGICAL-INEQUALITY': 4,             
                                                'OBJECTIFICATION': 5}
                                    
                                    def convert_list(lst, mapping):
                                        return [mapping[l] for l in lst]
                                    
                                    task_data['hard_label'] = task_data['hard_label'].apply(convert_list, mapping=mapping)

                                    inverse_mapping = {0: 'sexual-violence',
                                                    1: 'stereotyping-dominance',
                                                    2: 'non-sexist',
                                                    3: 'misogyny-non-sexual-violence',
                                                    4: 'ideological-inequality',
                                                    5: 'objectification'}
                                    
                                    
                                    # Set the mask to 1 if the label is present
                                    def create_mask(lst):
                                        mask = [0, 0, 0, 0, 0, 0]
                                        for label in lst:
                                            mask[label] = 1
                                        return mask
                                    
                                    # Create a new column with the mask
                                    task_data['label_task3_hf'] = task_data['hard_label'].apply(create_mask)
                                    # Cast to float
                                    task_data['label_task3_hf'] = task_data['label_task3_hf'].apply(lambda x: [float(i) for i in x])

                                    def create_map_from_mask(mask):
                                        return dict(zip([inverse_mapping[key] for key in sorted(inverse_mapping.keys())], mask))
                                    
                                    task_data['map_label_task3_hf'] = task_data['label_task3_hf'].apply(create_map_from_mask)

                                    # Rename hard_label to label
                                    task_data = task_data.rename(columns={'hard_label': 'label_task3'})    
                                
                            elif training_mode == 'soft':
                                if eval_mode != 'soft':
                                    continue
                                # Drop hard label
                                task_data = task_data.drop(columns=['hard_label'])
                                # Convert soft label
                                if task == 1:
                                    # Convert keys in soft label from YES/NO to 0/1
                                    soft_label_mapping = {'YES': 'sexist', 'NO': 'non-sexist'}
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                    # Convert soft_label to a list, ensuring the order of the labels
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: [x['non-sexist'], x['sexist']])
                                    # Set column label_text to ['non-sexist', 'sexist']
                                    task_data['label_text'] = [['non-sexist', 'sexist']] * len(task_data)
                                elif task == 2:
                                    soft_label_mapping = {'DIRECT': 'direct', 'REPORTED': 'reported', 'JUDGEMENTAL': 'judgemental', 'NO': 'non-sexist'}
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                    # Convert soft_label to a list, ensuring the order of the labels
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: [x['non-sexist'], x['judgemental'], x['reported'], x['direct']])
                                    # Set column label_text to ['non-sexist', 'judgemental', 'reported', 'direct']
                                    task_data['label_text'] = [['non-sexist', 'judgemental', 'reported', 'direct']] * len(task_data)
                                elif task == 3:
                                    soft_label_mapping = {'SEXUAL-VIOLENCE': 'sexual-violence',
                                                        'STEREOTYPING-DOMINANCE': 'stereotyping-dominance',
                                                        'NO': 'non-sexist',
                                                        'MISOGYNY-NON-SEXUAL-VIOLENCE': 'misogyny-non-sexual-violence',
                                                        'IDEOLOGICAL-INEQUALITY': 'ideological-inequality',
                                                        'OBJECTIFICATION': 'objectification'}
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: {soft_label_mapping[k]: v for k, v in x.items()})
                                    # Convert soft_label to a list, ensuring the order of the labels
                                    task_data['soft_label'] = task_data['soft_label'].apply(lambda x: [x['sexual-violence'], 
                                                                                                       x['stereotyping-dominance'],
                                                                                                       x['non-sexist'],
                                                                                                       x['misogyny-non-sexual-violence'], 
                                                                                                       x['ideological-inequality'], 
                                                                                                       x['objectification']])
                                    # Set column label_text to ['sexual-violence', 'stereotyping-dominance', 'non-sexist', 'misogyny-non-sexual-violence', 'ideological-inequality', 'objectification']
                                    task_data['label_text'] = [['sexual-violence', 
                                                                'stereotyping, dominance', 
                                                                'non-sexist', 
                                                                'misogyny-non-sexual-violence', 
                                                                'ideological-inequality', 
                                                                'objectification']] * len(task_data)
                                    
                                # Rename soft_label to label
                                task_data = task_data.rename(columns={'soft_label': 'label'})
                                
                            else:
                                raise ValueError(f'Invalid training_mode: {training_mode}')
                            output_file_path = task_output_folder / f'{split}_{lang}.json'
                            if split == 'dev':
                                output_file_path = output_file_path.with_name(output_file_path.name.replace('dev', 'val'))
                            task_data['test_case'] = 'EXIST2023'
                            task_data.to_json(output_file_path, orient='records', force_ascii=False, indent=4)

def main():
    args = parse_arguments()

    train_file_path = args.train_file_path
    dev_file_path = args.dev_file_path
    test_file_path = args.test_file_path
    gold_folder = args.gold_folder
    output_folder = args.output_folder

    # Print the arguments
    print(f'train_file_path: {train_file_path}')
    print(f'dev_file_path: {dev_file_path}')
    print(f'test_file_path: {test_file_path}')
    print(f'gold_folder: {gold_folder}')
    print(f'output_folder: {output_folder}')
    

    pl.Path(output_folder).mkdir(parents=True, exist_ok=True)

    split_data = load_split_data(train_file_path, dev_file_path, test_file_path)
    gold_data = load_gold_data(gold_folder)
    split_data = join_gold_data_to_split_data(split_data, gold_data)
    save_data_to_json(split_data, output_folder)

if __name__ == "__main__":
    main()