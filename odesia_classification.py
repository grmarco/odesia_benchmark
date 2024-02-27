import os
import numpy as np

from datasets import ClassLabel

from transformers import AutoModelForTokenClassification, DataCollatorForTokenClassification
from transformers import AutoModelForSequenceClassification, DataCollatorWithPadding
from transformers import pipeline

import evaluate
from sklearn.metrics import f1_score, accuracy_score

from odesia_core import OdesiaHFModel

import pandas as pd

from vendor.exist2023evaluation import ICM_Hard


class OdesiaUniversalClassification(OdesiaHFModel):
    def __init__(self, model_path, dataset_path, model_config, dataset_config):
        super().__init__(model_path, dataset_path, model_config, dataset_config)
        
        # processing labels
        self.label2id = dataset_config['label2id']
        self.id2label = {v: k for k, v in self.label2id.items()}
        self.label_list = list(self.label2id.keys())
        self.num_labels = len(dataset_config['label2id'])

class OdesiaTokenClassification(OdesiaUniversalClassification):

    def __init__(self, model_path, dataset_path, model_config, dataset_config):
        super().__init__(model_path, dataset_path, model_config, dataset_config)
               
        # Step 1. Load DataCollator            
        self.data_collator = DataCollatorForTokenClassification(tokenizer=self.tokenizer)
        
        # Step 2. Tokenized the dataset
        if not self.tokenized_dataset:           
            self.tokenized_dataset = self.dataset.map(self.tokenize_and_align_labels, batched=True)
            self.tokenized_dataset.save_to_disk(self.dataset_path_tokenized)
           
        # Step 3. Loading model, trainer and metrics
        self.seqeval = evaluate.load("seqeval")

        self.model = AutoModelForTokenClassification.from_pretrained(
            self.model_path, num_labels=self.num_labels, id2label=self.id2label, label2id=self.label2id
        )        

        self.trainer = self.load_trainer(model=self.model, 
                                         data_collator=self.data_collator, 
                                         tokenized_dataset=self.tokenized_dataset, 
                                         compute_metrics_function=self.compute_metrics)
        

        
    def tokenize_and_align_labels_bugeada(self, examples):
        tokenized_inputs = self.tokenizer(examples["tokens"], 
                                          is_split_into_words=True, 
                                          padding='max_length', 
                                          truncation=True, 
                                          max_length=self.tokenizer.model_max_length,
                                          return_tensors="pt")
        labels = []
        for i, label in enumerate(examples[f"ner_tags_index"]):
            word_ids = tokenized_inputs.word_ids(batch_index=i)  # Map tokens to their respective word.
            previous_word_idx = None
            label_ids = []
            for word_idx in word_ids:  # Set the special tokens to -100.
                if word_idx is None:
                    label_ids.append(-100)
                elif word_idx != previous_word_idx:  # Only label the first token of a given word.
                    label_ids.append(label[word_idx])
                else:
                    label_ids.append(-100)
                previous_word_idx = word_idx
            label_ids = label_ids
            labels.append(label_ids)

        tokenized_inputs["labels"] = labels

        return tokenized_inputs
    
    def tokenize_and_align_labels(self, examples, label_all_tokens=True):
        texts = examples["tokens"]  
        tags = examples["ner_tags"] 
        tokenized_inputs = self.tokenizer(texts,
                                    is_split_into_words=True,
                                    # return_offsets_mapping=True,
                                    padding=True, truncation=True)
        if tags is not None:
            raw_labels = [[self.label2id[tag] for tag in doc] for doc in tags]
            labels = []
            for i, raw_label in enumerate(raw_labels):
                word_ids = tokenized_inputs.word_ids(batch_index=i)
                previous_word_idx = None
                label = []
                for word_idx in word_ids:
                    # Special tokens have a word id that is None. We set the label to -100 so they are automatically
                    # ignored in the loss function.
                    if word_idx is None:
                        label.append(-100)
                    # We set the label for the first token of each word.
                    elif word_idx != previous_word_idx:
                        label.append(raw_label[word_idx])
                    # For the other tokens in a word, we set the label to either the current label or -100, depending on
                    # the label_all_tokens flag.
                    else:
                        label.append(raw_label[word_idx] if label_all_tokens else -100)
                    previous_word_idx = word_idx
                labels.append(label)
            tokenized_inputs["labels"] = labels
        return tokenized_inputs
    
    def compute_metrics(self, p):
        predictions, labels = p
        predictions = np.argmax(predictions, axis=2)

        true_predictions = [
            [self.label_list[p] for (p, l) in zip(prediction, label) if l != -100]
            for prediction, label in zip(predictions, labels)
        ]
        true_labels = [
            [self.label_list[l] for (p, l) in zip(prediction, label) if l != -100]
            for prediction, label in zip(predictions, labels)
        ]

        results = self.seqeval.compute(predictions=true_predictions, references=true_labels)
        return {
            "precision": results["overall_precision"],
            "recall": results["overall_recall"],
            "f1": results["overall_f1"],
            "accuracy": results["overall_accuracy"],
        }
    
    def predict(self, split="test"):
        results = []
        input_ner = self.tokenized_dataset[split].select(range(30))
        print(input_ner[0])
        p = self.trainer.predict(input_ner)

        predictions, labels = p.predictions, p.label_ids
        predictions = np.argmax(predictions, axis=2)

        true_predictions = [
            [self.label_list[p] for p in prediction]
            for prediction in predictions
        ]
      

        for input, true_prediction in zip(self.dataset[split], true_predictions): 
            if not true_prediction:
                true_prediction = [""]
            result = {"test_case": self.test_case,
                            "id": input["id"],
                            "ner_tags": list(true_prediction)}
            
            results.append(result)
        return true_predictions
    
    def predict_evall_format(self, split="test"):
        inputs = self.dataset[split].select(range(30))
        classifier = pipeline("ner", model=self.model.to('cpu'), tokenizer=self.tokenizer)
       
        results = []
        for input in inputs:
            input_tokens = input['tokens']
            ner_tags = [None for _ in input_tokens]
            ner_tags_index = [None for _ in input_tokens]

            text = ' '.join(input_tokens)
            classifier_outputs = classifier(text)
            # si clasifica los tokens
            if classifier_outputs:
                # para ese ejemplo vamos token por token
                for classifier_output in classifier_outputs:
                    # sacamos la palabra clasificada
                    start = classifier_output["start"]
                    end = classifier_output["start"]+len(classifier_output["word"].replace("##", ""))
                    tag = classifier_output["entity"]
                    token_result = text[start:end]
                    
                    for i, input_token in enumerate(input_tokens):
                        if token_result == input_token:
                            ner_tags[i] = tag
                            ner_tags_index[i] = self.label2id[tag]

                ner_tags = [ner_tag if ner_tag else 'O' for ner_tag in ner_tags]
                ner_tags_index = [ner_tag_index if ner_tag_index else self.label2id['O'] for ner_tag_index in ner_tags_index]



                result = {"test_case": self.test_case,
                        "id":input["id"],
                        "classifier_output": classifier_outputs,
                        "gold_ner_tags" : input["ner_tags"],
                        "gold_tokens" : input['tokens'],
                        "ner_tags":ner_tags, 
                        "ner_tags_index":ner_tags_index}
                                               
                results.append(result)   
        return {split:results}
    
    
    
class OdesiaTextClassification(OdesiaUniversalClassification):
    
    def __init__(self, model_path, dataset_path, model_config, dataset_config):                
        super().__init__(model_path, dataset_path, model_config, dataset_config)
        
        # Step 1. Load DataCollator            
        self.data_collator = DataCollatorWithPadding(tokenizer=self.tokenizer)        

        # Step 2. Tokenized the dataset

        # renaming the column label
        column_names = self.dataset['train'].column_names
        if 'label' in column_names and dataset_config["label_column"].strip() != 'label':
            self.dataset = self.dataset.rename_column('label', "label_old")        
        self.dataset = self.dataset.rename_column(dataset_config["label_column"], "label")

        if not self.tokenized_dataset:            
            # para clasificación multiclase o binaria
            if self.problem_type != 'multi_label_classification':
                self.dataset = self.dataset.cast_column('label', ClassLabel(names=self.label_list))
            self.tokenized_dataset = self.dataset.map(lambda ex: self.tokenizer(ex["text"], truncation=True, padding=True), batched=True)
            self.tokenized_dataset.save_to_disk(self.dataset_path_tokenized)

        # Step 3. Loading model, trainer and metrics
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, 
            num_labels=self.num_labels, 
            problem_type = 'multi_label_classification' if self.problem_type == 'multi_label_classification' else None
        )

        self.trainer = self.load_trainer(model=self.model, 
                                         data_collator=self.data_collator, 
                                         tokenized_dataset=self.tokenized_dataset, 
                                         compute_metrics_function=self.compute_metrics)

    def convert_predictions(self, pred):
        if 'multi_class_classification' in self.problem_type:
            predictions = np.argmax(pred.predictions, axis=-1)
        elif 'multi_label_classification' in self.problem_type:
            probs = 1 / (1 + np.exp(-pred.predictions))
            predictions = (probs > 0.5).astype(int)
        else:
            raise ValueError(f"Problem type {self.problem_type} not supported")
        return predictions

    def compute_metrics(self, pred):
        labels = pred.label_ids
        predictions = self.convert_predictions(pred)

        f1_scores = f1_score(labels, predictions, average=None).tolist()
        f1_macro = f1_score(labels, predictions, average="macro").tolist()
        accuracy = accuracy_score(labels, predictions)

        return {
            "accuracy": accuracy,
            "f1_macro": f1_macro,
            "f1_per_class": {label_f1: f1_value for label_f1, f1_value in zip(self.label_list, f1_scores)}
        }

    def predict(self, split="test"):
        results = []
        dataset = self.tokenized_dataset[split]
        pred = self.trainer.predict(dataset)
        predictions = self.convert_predictions(pred)

        for i, prediction in enumerate(predictions):
            if 'multi_class_classification' in self.problem_type:
                predicted_labels = self.id2label[int(prediction)]
            elif 'multi_label_classification' in self.problem_type:
                predicted_labels = [self.id2label[j] for j, label_id in enumerate(prediction) if label_id == 1]
            else:
                raise ValueError(f"Problem type {self.problem_type} not supported")
        
            result = {
                'test_case': self.test_case,
                'id': dataset[i]['id'],
                'label': predicted_labels
            }
            results.append(result)
        return {split: results}
            
class OdesiaTextClassificationWithDisagreements(OdesiaTextClassification):
    
    def __init__(self, model_path, dataset_path, model_config, dataset_config):                
        super().__init__(model_path, dataset_path, model_config, dataset_config)
        

    def compute_metrics(self, pred):
        base_metrics = super().compute_metrics(pred)
        
        labels = pred.label_ids
        predictions = self.convert_predictions(pred)

        # Convert to pandas dataframe 
        predictions_df = pd.DataFrame(predictions, columns=['value'])
        labels_df = pd.DataFrame(labels, columns=['value'])

        # Create column 'id' for predictions_df and labels_df
        predictions_df['id'] = predictions_df.index
        labels_df['id'] = labels_df.index
        
        # Compute ICM_Hard (needs to be converted into pandas dataframe)
        icm_hard =  ICM_Hard(predictions_df, labels_df, "task1", None)
        icm_hard_result = icm_hard.evaluate()

        ## Add results to base_metrics
        base_metrics['icm_hard'] = icm_hard_result
        return base_metrics

