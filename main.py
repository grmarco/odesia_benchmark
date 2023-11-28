import os
import time
#os.environ["CUDA_VISIBLE_DEVICES"] = '1'
from odesia_evaluate_model import odesia_benchmark


def main():
    # big models 
    big_language_models = {'es':['PlanTL-GOB-ES/roberta-large-bne','xlm-roberta-large', 'xlm-roberta-base',],
                        'en':['roberta-large', 'xlm-roberta-base', 'xlm-roberta-large',],
                    
            } 
    
    # small models
    language_models = {'es':['bertin-project/bertin-roberta-base-spanish', 'bert-base-multilingual-cased', 
                             'distilbert-base-multilingual-cased', 'CenIA/distillbert-base-spanish-uncased',  
                             'PlanTL-GOB-ES/roberta-base-bne', 'dccuchile/bert-base-spanish-wwm-cased', 'ixa-ehu/ixambert-base-cased',                        
                        ],
                        'en':['bert-base-cased', 'distilbert-base-uncased', 
                              'bert-base-multilingual-cased', 'distilbert-base-multilingual-cased', 
                              'ixa-ehu/ixambert-base-cased'                                                 
                             ],
                    
            }

    '''hparams_to_search = {
            'per_device_train_batch_size' : [8],
            'gradient_accumulation_steps' : [4, 2],
            'learning_rate': [0.00001, 0.00003, 0.00005],
            'weight_decay': [0.1, 0.01]
        }'''
    hparams_to_search = {
            'per_device_train_batch_size' : [32, 16],
            'learning_rate': [0.00001, 0.00003, 0.00005],
            'weight_decay': [0.1, 0.01]
        }
    total_iterations = len(language_models['es'])+len(language_models['en'])
    current_iterations = 0
    for language in language_models:
        
        for model in language_models[language]:
            
            start_time = time.time()
            
            odesia_benchmark(model=model, 
                             language=language, 
                             grid_search=hparams_to_search, 
                             datasets_to_eval=['exist_2022_t1', 'exist_2022_t2','mldoc_2018', 'sts_2017']
            )
            
            # calculamos el tiempo de esta ejecucion
            iteration_time = time.time() - start_time

            remaining_time_estimate = iteration_time * (total_iterations - current_iterations - 1)

            days = int(remaining_time_estimate // (24 * 3600))
            hours = int((remaining_time_estimate % (24 * 3600)) // 3600)
            minutes = int((remaining_time_estimate % 3600) // 60)
            seconds = int(remaining_time_estimate % 60)
            current_iterations += 1
            print("##############################")
            print("##############################")
            print(f"Model {current_iterations}/{total_iterations} - Estimated remaining based in the last model {model}: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds")
            print("##############################")
            print("##############################")
            
                
    
    
if __name__ == "__main__":
    main()