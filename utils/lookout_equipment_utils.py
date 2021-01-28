# Standard python and AWS imports:
import boto3
import json
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import pprint
import time
import uuid

from botocore.config import Config
from matplotlib.dates import DateFormatter
from matplotlib import gridspec
from scipy.stats import wasserstein_distance
from typing import List, Dict
from tqdm import tqdm

# Parameters
DEFAULT_REGION = 'eu-west-1'

def get_client(region_name=DEFAULT_REGION):
    """
    Get a boto3 client for the Amazon Lookout for Equipment service.
    
    PARAMS
    ======
        region_name: string
            AWS region name. (Default: eu-west-1)
    
    RETURN
    ======
        lookoutequipment_client
            A boto3 client to interact with the L4E service
    """
    lookoutequipment_client = boto3.client(
        service_name='lookoutequipment',
        region_name=region_name,
        config=Config(connect_timeout=30, read_timeout=30, retries={'max_attempts': 3}),
        endpoint_url=f'https://lookoutequipment.{region_name}.amazonaws.com/'
    )
    
    return lookoutequipment_client


def list_datasets(
    dataset_name_prefix=None,
    max_results=50,
    region_name=DEFAULT_REGION
):
    """
    List all the Lookout for Equipment datasets available in this account.
    
    PARAMS
    ======
        dataset_name_prefix: string
            Prefix to filter out all the datasets which names starts by 
            this prefix. Defaults to None to list all datasets.
            
        max_results: integer (default: 50)
            Max number of datasets to return 
            
        region_name: string
            AWS region name. (Default: eu-west-1)
            
    RETURN
    ======
        dataset_list: list of strings
            A list with all the dataset names found in the current region
    """
    # Initialization:
    dataset_list = []
    has_more_records = True
    lookoutequipment_client = get_client(region_name=region_name)
    
    # Building the request:
    kargs = {"MaxResults": max_results}
    if dataset_name_prefix is not None:
        kargs["DatasetNameBeginsWith"] = dataset_name_prefix
    
    # We query for the list of datasets, until there are none left to fetch:
    while has_more_records:
        # Query for the list of L4E datasets available for this AWS account:
        list_datasets_response = lookoutequipment_client.list_datasets(**kargs)
        if "NextToken" in list_datasets_response:
            kargs["NextToken"] = list_datasets_response["NextToken"]
        else:
            has_more_records = False
        
        # Add the dataset names to the list:
        dataset_summaries = list_datasets_response["DatasetSummaries"]
        for dataset_summary in dataset_summaries:
            dataset_list.append(dataset_summary['DatasetName'])
    
    return dataset_list

def list_models_for_datasets(
    model_name_prefix=None, 
    dataset_name_prefix=None,
    max_results=50,
    region_name=DEFAULT_REGION
):
    """
    List all the models available in a given region.
    
    PARAMS
    ======
        model_name_prefix: string (default: None)
            Prefix to filter on the model name to look for
            
        dataset_name_prefix: string (default None)
            Prefix to filter the dataset name: if used, only models
            making use of this particular dataset are returned

        max_results: integer (default: 50)
            Max number of datasets to return 
            
    RETURNS
    =======
        models_list: list of string
            List of all the models corresponding to the input parameters
            (regions and dataset)
    """
    # Initialization:
    models_list = []
    has_more_records = True
    lookoutequipment_client = get_client(region_name=region_name)
    
    # Building the request:
    list_models_request = {"MaxResults": max_results}
    if model_name_prefix is not None:
        list_models_request["ModelNameBeginsWith"] = model_name_prefix
    if dataset_name_prefix is not None:
        list_models_request["DatasetNameBeginsWith"] = dataset_name_prefix

    # We query for the list of models, until there are none left to fetch:
    while has_more_records:
        # Query for the list of L4E models available for this AWS account:
        list_models_response = lookoutequipment_client.list_models(**list_models_request)
        if "NextToken" in list_models_response:
            list_models_request["NextToken"] = list_models_response["NextToken"]
        else:
            has_more_records = False

        # Add the model names to the list:
        model_summaries = list_models_response["ModelSummaries"]
        for model_summary in model_summaries:
            models_list.append(model_summary['ModelName'])

    return models_list


def create_dataset(
    dataset_name, 
    dataset_schema, 
    region_name=DEFAULT_REGION
):
    """
    Creates a Lookout for Equipment dataset
    
    PARAMS
    ======
        dataset_name: string
            Name of the dataset to be created.
            
        dataset_schema: string
            JSON-formatted string describing the data schema the dataset
            must conform to.
            
        dataset_schema: string
            JSON formatted string to describe the dataset schema
    """
    # Initialization:
    lookoutequipment_client = get_client(region_name=region_name)
    has_more_records = True
    pp = pprint.PrettyPrinter(depth=4)

    # Checks if the dataset already exists:
    list_datasets_response = lookoutequipment_client.list_datasets(
        DatasetNameBeginsWith=dataset_name
    )

    dataset_exists = False
    for dataset_summary in list_datasets_response['DatasetSummaries']:
        if dataset_summary['DatasetName'] == dataset_name:
            dataset_exists = True
            break

    # If the dataset exists we just returns that message:
    if dataset_exists:
        print(f'Dataset "{dataset_name}" already exists and can be used to ingest data or train a model.')

    # Otherwise, we create it:
    else:
        print(f'Dataset "{dataset_name}" does not exist, creating it...\n')

        try:
            client_token = uuid.uuid4().hex
            data_schema = { 'InlineDataSchema': dataset_schema }
            create_dataset_response = lookoutequipment_client.create_dataset(
                DatasetName=dataset_name,
                DatasetSchema=data_schema,
                ClientToken=client_token
            )

            print("=====Response=====\n")
            pp.pprint(create_dataset_response)
            print("\n=====End of Response=====")

        except Exception as e:
            print(e)
            

def ingest_data(data_ingestion_role_arn, dataset_name, bucket, prefix, region_name=DEFAULT_REGION):
    lookoutequipment_client = get_client(region_name=region_name)
    ingestion_input_config = dict()
    ingestion_input_config['S3InputConfiguration'] = dict(
        [
            ('Bucket', bucket),
            ('Prefix', prefix)
        ]
    )

    client_token = uuid.uuid4().hex

    # Start data ingestion
    start_data_ingestion_job_response = lookoutequipment_client.start_data_ingestion_job(
        DatasetName=dataset_name,
        RoleArn=data_ingestion_role_arn, 
        IngestionInputConfiguration=ingestion_input_config,
        ClientToken=client_token)

    data_ingestion_job_id = start_data_ingestion_job_response['JobId']
    data_ingestion_status = start_data_ingestion_job_response['Status']
    
    return data_ingestion_job_id, data_ingestion_status


def delete_dataset(DATASET_NAME, region_name=DEFAULT_REGION):
    lookoutequipment_client = get_client(region_name=region_name)
    
    try:
        delete_dataset_response = lookoutequipment_client.delete_dataset(DatasetName=DATASET_NAME)
        print(f'Dataset "{DATASET_NAME}" is deleted successfully.')
        
    except Exception as e:
        error_code = e.response['Error']['Code']
        if (error_code == 'ConflictException'):
            print('Dataset is used by at least a model, deleting the associated model(s) before deleting dataset.')
            models_list = list_models_for_datasets(DATASET_NAME_FOR_LIST_MODELS=DATASET_NAME)

            for model_name_to_delete in models_list:
                delete_model_response = lookoutequipment_client.delete_model(ModelName=model_name_to_delete)
                print(f'- Model "{model_name_to_delete}" is deleted successfully.')
                
            delete_dataset_response = lookoutequipment_client.delete_dataset(DatasetName=DATASET_NAME)
            print(f'Dataset "{DATASET_NAME}" is deleted successfully.')

        elif (error_code == 'ResourceNotFoundException'):
            print(f'Dataset "{DATASET_NAME}" not found: creating a dataset with this name is possible.')

            
def create_data_schema(component_fields_map: Dict):
    return json.dumps(_create_data_schema_map(component_fields_map=component_fields_map))

def _create_data_schema_map(component_fields_map: Dict):
    data_schema = dict()
    component_schema_list = list()
    data_schema['Components'] = component_schema_list

    for component_name in component_fields_map:
        component_schema = _create_component_schema(component_name, component_fields_map[component_name])
        component_schema_list.append(component_schema)

    return data_schema

def _create_component_schema(component_name: str, field_names: List):
    component_schema = dict()
    component_schema['ComponentName'] = component_name
    col_list = []
    component_schema['Columns'] = col_list

    is_first_field = True
    for field_name in field_names:
        if is_first_field:
            ts_col = dict()
            ts_col['Name'] = field_name
            ts_col['Type'] = 'DATETIME'
            col_list.append(ts_col)
            is_first_field = False
        else:
            attr_col = dict()
            attr_col['Name'] = field_name
            attr_col['Type'] = 'DOUBLE'
            col_list.append(attr_col)
    return component_schema
    
def plot_timeseries(timeseries_df, tag_name, 
                    start=None, end=None, 
                    plot_rolling_avg=False, 
                    labels_df=None, 
                    predictions=None,
                    tag_split=None,
                    custom_grid=True,
                    fig_width=18,
                    prediction_titles=None
                   ):
    """
    This function plots a time series signal with a line plot and can combine
    this with labelled and predicted anomaly ranges.
    
    PARAMS
    ======
        timeseries_df: pandas.DataFrame
            A dataframe containing the time series to plot
        
        tag_name: string
            The name of the tag that we can add in the label
        
        start: string or pandas.Datetime (default: None)
            Starting timestamp of the signal to plot. If not provided, will use
            the whole signal
        
        end: string or pandas.Datetime (default: None)
            End timestamp of the signal to plot. If not provided, will use the
            whole signal
        
        plot_rolling_avg: boolean (default: False)
            If set to true, will add a rolling average curve on top of the
            line plot for the time series.
        
        labels_df: pandas.DataFrame (default: None)
            If provided, this is a dataframe with all the labelled anomalies.
            This will be rendered as a filled-in plots below the time series
            itself.
        
        predictions: pandas.DataFrame or list of pandas.DataFrame
            If provided, this is a dataframe with all the predicted anomalies.
            This will be rendered as a filled-in plots below the time series
            itself.
            
        tag_split: string or pandas.Datetime
            If provided, the line plot will plot the first part of the time
            series with a colour and the second part in grey. This can be
            used to show the split between training and evaluation period for
            instance.
        
        custom_grid: boolean (default: True)
            Will show a custom grid with month name mentionned for each quarter
            and lighter lines for the other month to prevent clutter on the
            horizontal axis.
        
        fig_width: integer (default: 18)
            Figure width.
        
        prediction_titles: list of strings (default: None)
            If we want to plot multiple predictions, we can set the titles for
            each of the prediction plot.
    
    RETURNS
    =======
        fig: matplotlib.pyplot.figure
            A figure where the plots are drawn
            
        ax: matplotlib.pyplot.Axis
            An axis where the plots are drawn
    """
    if start is None:
        start = timeseries_df.index.min()
    elif type(start) == str:
        start = pd.to_datetime(start)
        
    if end is None:
        end = timeseries_df.index.max()
    elif type(end) == str:
        end = pd.to_datetime(end)
        
    if (tag_split is not None) & (type(tag_split) == str):
        tag_split = pd.to_datetime(tag_split)

    # Prepare the figure:
    fig_height = 4
    height_ratios = [8]
    nb_plots = 1
    
    if labels_df is not None:
        fig_height += 1
        height_ratios += [1.5]
        nb_plots += 1
        
    if predictions is not None:
        if type(predictions) == pd.core.frame.DataFrame:
            fig_height += 1
            height_ratios += [1.5]
            nb_plots += 1
        elif type(predictions) == list:
            fig_height += 1 * len(predictions)
            height_ratios = height_ratios + [1.5] * len(predictions)
            nb_plots += len(predictions)
            
    fig = plt.figure(figsize=(fig_width, fig_height))
    gs = gridspec.GridSpec(nb_plots, 1, height_ratios=height_ratios, hspace=0.5)
    ax = []
    for i in range(nb_plots):
        ax.append(fig.add_subplot(gs[i]))
        
    # Plot the time series signal:
    data = timeseries_df[start:end].copy()
    if tag_split is not None:
        ax[0].plot(data.loc[start:tag_split, 'Value'], linewidth=0.5, alpha=0.5, label=f'{tag_name} - Training', color='tab:grey')
        ax[0].plot(data.loc[tag_split:end, 'Value'], linewidth=0.5, alpha=0.8, label=f'{tag_name} - Evaluation')
    else:
        ax[0].plot(data['Value'], linewidth=0.5, alpha=0.8, label=tag_name)
    ax[0].set_xlim(start, end)
    
    # Plot a daily rolling average:
    if plot_rolling_avg == True:
        daily_rolling_average = data['Value'].rolling(window=60*24).mean()
        ax[0].plot(data.index, daily_rolling_average, alpha=0.5, color='white', linewidth=3)
        ax[0].plot(data.index, daily_rolling_average, label='Daily rolling leverage', color='tab:red', linewidth=1)

    # Configure custom grid:
    ax_id = 0
    if custom_grid:
        date_format = DateFormatter("%Y-%m")
        major_ticks = np.arange(start, end, 3, dtype='datetime64[M]')
        minor_ticks = np.arange(start, end, 1, dtype='datetime64[M]')
        ax[ax_id].xaxis.set_major_formatter(date_format)
        ax[ax_id].set_xticks(major_ticks)
        ax[ax_id].set_xticks(minor_ticks, minor=True)
        ax[ax_id].grid(which='minor', axis='x', alpha=0.8)
        ax[ax_id].grid(which='major', axis='x', alpha=1.0, linewidth=2)
        ax[ax_id].xaxis.set_tick_params(rotation=30)

    # Add the labels on a second plot:
    if labels_df is not None:
        ax_id += 1
        label_index = pd.date_range(start=data.index.min(), end=data.index.max(), freq='1min')
        label_data = pd.DataFrame(index=label_index)
        label_data.loc[:, 'Label'] = 0.0

        for index, row in labels_df.iterrows():
            event_start = row['start']
            event_end = row['end']
            label_data.loc[event_start:event_end, 'Label'] = 1.0
            
        ax[ax_id].plot(label_data['Label'], color='tab:green', linewidth=0.5)
        ax[ax_id].set_xlim(start, end)
        ax[ax_id].fill_between(label_index, y1=label_data['Label'], y2=0, alpha=0.1, color='tab:green', label='Real anomaly range (label)')
        ax[ax_id].axes.get_xaxis().set_ticks([])
        ax[ax_id].axes.get_yaxis().set_ticks([])
        ax[ax_id].set_xlabel('Anomaly ranges (labels)', fontsize=12)
        
    # Add the labels (anomaly range) on a 
    # third plot located below the main ones:
    if predictions is not None:
        pred_index = pd.date_range(start=data.index.min(), end=data.index.max(), freq='1min')
        pred_data = pd.DataFrame(index=pred_index)
        
        if type(predictions) == pd.core.frame.DataFrame:
            ax_id += 1
            pred_data.loc[:, 'prediction'] = 0.0

            for index, row in predictions.iterrows():
                event_start = row['start']
                event_end = row['end']
                pred_data.loc[event_start:event_end, 'prediction'] = 1.0

            ax[ax_id].plot(pred_data['prediction'], color='tab:red', linewidth=0.5)
            ax[ax_id].set_xlim(start, end)
            ax[ax_id].fill_between(pred_index, 
                             y1=pred_data['prediction'],
                             y2=0, 
                             alpha=0.1, 
                             color='tab:red')
            ax[ax_id].axes.get_xaxis().set_ticks([])
            ax[ax_id].axes.get_yaxis().set_ticks([])
            ax[ax_id].set_xlabel('Anomaly ranges (Prediction)', fontsize=12)
            
        elif type(predictions) == list:
            for prediction_index, p in enumerate(predictions):
                ax_id += 1
                pred_data.loc[:, 'prediction'] = 0.0

                for index, row in p.iterrows():
                    event_start = row['start']
                    event_end = row['end']
                    pred_data.loc[event_start:event_end, 'prediction'] = 1.0
                
                ax[ax_id].plot(pred_data['prediction'], color='tab:red', linewidth=0.5)
                ax[ax_id].set_xlim(start, end)
                ax[ax_id].fill_between(pred_index,
                                 y1=pred_data['prediction'],
                                 y2=0, 
                                 alpha=0.1, 
                                 color='tab:red')
                ax[ax_id].axes.get_xaxis().set_ticks([])
                ax[ax_id].axes.get_yaxis().set_ticks([])
                ax[ax_id].set_xlabel(prediction_titles[prediction_index], fontsize=12)
        
    # Show the plot with a legend:
    ax[0].legend(fontsize=10, loc='upper right', framealpha=0.4)
        
    return fig, ax

class LookoutEquipmentAnalysis:
    """
    A class to manage Lookout for Equipment result analysis
    
    ATTRIBUTES
    ==========
        model_name: string
            The name of the Lookout for Equipment trained model
                
        predicted_ranges: pandas.DataFrame
            A Pandas dataframe with the predicted anomaly ranges listed in
            chronological order with a Start and End columns

        labelled_ranges: pandas.DataFrame
            A Pandas dataframe with the labelled anomaly ranges listed in
            chronological order with a Start and End columns

        df_list: list of pandas.DataFrame
            A list with each time series into a dataframe

    METHODS
    =======
        set_time_periods():
            Sets the time period used for the analysis of the model evaluations
            
        get_predictions():
            Get the anomaly ranges predicted by the current model
            
        get_labels():
            Get the labelled ranges as provided to the model before training
            
        compute_histograms():
            This method loops through each signal and computes two distributions
            of the values in the time series: one for all the anomalies found in
            the evaluation period and another one with all the normal values 
            found in the same period. It then ranks every signals based on the
            distance between these two histograms

        plot_histograms():
            Plot the top 12 signal values distribution by decreasing ranking 
            distance (as computed by the compute_histograms() method
            
        plot_signals():
            Plot the top 12 signals by decreasing ranking distance. For each 
            signal, this method will plot the normal values in green and the 
            anomalies in red

        get_ranked_list():
            Returns the list of signals with computed rank
    """
    def __init__(self, model_name, tags_df, region_name=DEFAULT_REGION):
        """
        Create a new analysis for a Lookout for Equipment model.
        
        PARAMS
        ======
            model_name: string
                The name of the Lookout for Equipment trained model
                
            tags_df: pandas.DataFrame
                A dataframe containing all the signals, indexed by time
                
            region_name: string
                Name of the AWS region from where the service is called.
        """
        self.lookout_client = get_client(region_name)
        self.model_name = model_name
        self.predicted_ranges = None
        self.labelled_ranges = None
        
        self.df_list = dict()
        for signal in tags_df.columns:
            self.df_list.update({signal: tags_df[[signal]]})
        
    def _load_model_response(self):
        """
        Use the trained model description to extract labelled and predicted 
        ranges of anomalies. This method will extract them from the 
        DescribeModel API from Lookout for Equipment and store them in the
        labelled_ranges and predicted_ranges properties.
        """
        describe_model_response = self.lookout_client.describe_model(ModelName=self.model_name)
        
        self.labelled_ranges = eval(describe_model_response['ModelMetrics'])['labeled_ranges']
        self.predicted_ranges = eval(describe_model_response['ModelMetrics'])['predicted_ranges']

        self.labelled_ranges = pd.DataFrame(self.labelled_ranges)
        self.labelled_ranges['start'] = pd.to_datetime(self.labelled_ranges['start'])
        self.labelled_ranges['end'] = pd.to_datetime(self.labelled_ranges['end'])

        self.predicted_ranges = pd.DataFrame(self.predicted_ranges)
        self.predicted_ranges['start'] = pd.to_datetime(self.predicted_ranges['start'])
        self.predicted_ranges['end'] = pd.to_datetime(self.predicted_ranges['end'])
        
    def set_time_periods(self, 
                         evaluation_start, 
                         evaluation_end, 
                         training_start, 
                         training_end):
        """
        Set the time period of analysis
        
        PARAMS
        ======
            evaluation_start: datetime
                Start of the evaluation period

            evaluation_end: datetime
                End of the evaluation period

            training_start: datetime
                Start of the training period

            training_end: datetime
                End of the training period
        """
        self.evaluation_start = evaluation_start
        self.evaluation_end = evaluation_end
        self.training_start = training_start
        self.training_end = training_end
    
    def get_predictions(self):
        """
        Get the anomaly ranges predicted by the current model
        
        RETURN
        ======
            predicted_ranges: pandas.DataFrame
                A Pandas dataframe with the predicted anomaly ranges listed in
                chronological order with a Start and End columns
        """
        if self.predicted_ranges is None:
            self._load_model_response()
            
        return self.predicted_ranges
        
    def get_labels(self):
        """
        Get the labelled ranges as provided to the model before training
        
        RETURN
        ======
            labelled_ranges: pandas.DataFrame
                A Pandas dataframe with the labelled anomaly ranges listed in
                chronological order with a Start and End columns
        """        
        if self.labelled_ranges is None:
            self._load_model_response()
            
        return self.labelled_ranges
    
    def _get_time_ranges(self):
        """
        Extract DateTimeIndex with normal values and anomalies from the
        predictions generated by the model.
        
        RETURNS
        =======
            index_normal: pandas.DateTimeIndex
                Timestamp index for all normal values
                
            index_anomaly: pandas.DateTimeIndex
                Timestamp index for all normal values
        """
        # Extract the first time series 
        tag = list(self.df_list.keys())[0]
        tag_df = self.df_list[tag]
        
        # Initialize the predictions dataframe:
        predictions_df = pd.DataFrame(columns=['Prediction'], index=tag_df.index)
        predictions_df['Prediction'] = 0

        # Loops through the predicted anomaly 
        # ranges and set these predictions to 1:
        for index, row in self.predicted_ranges.iterrows():
            predictions_df.loc[row['start']:row['end'], 'Prediction'] = 1

        # Limits the analysis range to the evaluation period:
        predictions_df = predictions_df[self.evaluation_start:self.evaluation_end]
        
        # Build a DateTimeIndex for normal values and anomalies:
        index_normal = predictions_df[predictions_df['Prediction'] == 0].index
        index_anomaly = predictions_df[predictions_df['Prediction'] == 1].index
        
        return index_normal, index_anomaly
    
    def compute_histograms(self, index_normal=None, index_anomaly=None, num_bins=20):
        """
        This method loops through each signal and computes two distributions of
        the values in the time series: one for all the anomalies found in the
        evaluation period and another one with all the normal values found in the
        same period. It then computes the Wasserstein distance between these two
        histograms and then rank every signals based on this distance. The higher
        the distance, the more different a signal is when comparing anomalous
        and normal periods. This can orient the investigation of a subject 
        matter expert towards the sensors and associated components.
        
        PARAMS
        ======
            index_normal: pandas.DateTimeIndex
                All the normal indices
                
            index_anomaly: pandas.DateTimeIndex
                All the indices for anomalies
                
            num_bins: integer (default: 20)
                Number of bins to use to build the distributions
        """
        if (index_normal is None) or (index_anomaly is None):
            self.ts_normal_training, self.ts_label_evaluation = self._get_time_ranges()

        self.num_bins = num_bins

        # Now we loop on each signal to compute a 
        # histogram of each of them in this anomaly range,
        # compte another one in the normal range and
        # compute a distance between these:
        rank = dict()
        for tag, current_tag_df in tqdm(self.df_list.items(), desc='Computing distributions'):
            try:
                # Get the values for the whole signal, parts
                # marked as anomalies and normal part:
                current_signal_values = current_tag_df[tag]
                current_signal_evaluation = current_tag_df.loc[self.ts_label_evaluation, tag]
                current_signal_training = current_tag_df.loc[self.ts_normal_training, tag]

                # Let's compute a bin width based on the whole range of possible 
                # values for this signal (across the normal and anomalous periods).
                # For both normalization and aesthetic reasons, we want the same
                # number of bins across all signals:
                bin_width = (np.max(current_signal_values) - np.min(current_signal_values))/self.num_bins
                bins = np.arange(np.min(current_signal_values), np.max(current_signal_values) + bin_width, bin_width)

                # We now use the same bins arrangement for both parts of the signal:
                u = np.histogram(current_signal_training, bins=bins, density=True)[0]
                v = np.histogram(current_signal_evaluation, bins=bins, density=True)[0]

                # Wasserstein distance is the earth mover distance: it can be 
                # used to compute a similarity between two distributions: this
                # metric is only valid when the histograms are normalized (hence
                # the density=True in the computation above):
                d = wasserstein_distance(u, v)
                rank.update({tag: d})

            except Exception as e:
                rank.update({tag: 0.0})

        # Sort histograms by decreasing Wasserstein distance:
        rank = {k: v for k, v in sorted(rank.items(), key=lambda rank: rank[1], reverse=True)}
        self.rank = rank
        
    def plot_histograms(self, nb_cols=3, max_plots=12):
        """
        Once the histograms are computed, we can plot the top N by decreasing 
        ranking distance. By default, this will plot the histograms for the top
        12 signals, with 3 plots per line.
        
        PARAMS
        ======
            nb_cols: integer (default: 3)
                Number of plots to assemble on a given row
                
            max_plots: integer (default: 12)
                Number of signal to consider
        """
        # Prepare the figure:
        nb_rows = len(self.df_list.keys()) // nb_cols + 1
        plt.style.use('Solarize_Light2')
        prop_cycle = plt.rcParams['axes.prop_cycle']
        colors = prop_cycle.by_key()['color']
        fig = plt.figure(figsize=(16, int(nb_rows * 3)))
        gs = gridspec.GridSpec(nb_rows, nb_cols, hspace=0.5, wspace=0.25)

        # Loops through each signal by decreasing distance order:
        i = 0
        for tag, current_rank in tqdm(self.rank.items(), total=max_plots, desc='Preparing histograms'):
            # We stop after reaching the number of plots we are interested in:
            if i > max_plots - 1:
                break

            try:
                # Get the anomaly and the normal values from the current signal:
                current_signal_values = self.df_list[tag][tag]
                current_signal_evaluation = self.df_list[tag].loc[self.ts_label_evaluation, tag]
                current_signal_training = self.df_list[tag].loc[self.ts_normal_training, tag]

                # Compute the bin width and bin edges to match the 
                # number of bins we want to have on each histogram:
                bin_width =(np.max(current_signal_values) - np.min(current_signal_values))/self.num_bins
                bins = np.arange(np.min(current_signal_values), np.max(current_signal_values) + bin_width, bin_width)

                # Add both histograms in the same plot:
                ax1 = plt.subplot(gs[i])
                ax1.hist(current_signal_training, 
                         density=True, 
                         alpha=0.5, 
                         color=colors[1], 
                         bins=bins, 
                         edgecolor='#FFFFFF')
                ax1.hist(current_signal_evaluation, 
                         alpha=0.5, 
                         density=True, 
                         color=colors[5], 
                         bins=bins, 
                         edgecolor='#FFFFFF')

            except Exception as e:
                print(e)
                ax1 = plt.subplot(gs[i])

            # Removes all the decoration to leave only the histograms:
            ax1.grid(False)
            ax1.get_yaxis().set_visible(False)
            ax1.get_xaxis().set_visible(False)

            # Title will be the tag name followed by the score:
            title = tag
            title += f' (score: {current_rank:.02f})'
            plt.title(title, fontsize=10)

            i+= 1
            
    def plot_signals(self, nb_cols=3, max_plots=12):
        """
        Once the histograms are computed, we can plot the top N signals by 
        decreasing ranking distance. By default, this will plot the signals for 
        the top 12 signals, with 3 plots per line. For each signal, this method
        will plot the normal values in green and the anomalies in red.
        
        PARAMS
        ======
            nb_cols: integer (default: 3)
                Number of plots to assemble on a given row
                
            max_plots: integer (default: 12)
                Number of signal to consider
        """
        # Prepare the figure:
        nb_rows = max_plots // nb_cols + 1
        plt.style.use('Solarize_Light2')
        prop_cycle = plt.rcParams['axes.prop_cycle']
        colors = prop_cycle.by_key()['color']
        fig = plt.figure(figsize=(28, int(nb_rows * 4)))
        gs = gridspec.GridSpec(nb_rows, nb_cols, hspace=0.5, wspace=0.25)
        
        # Loops through each signal by decreasing distance order:
        i = 0
        for tag, current_rank in self.rank.items():
            # We stop after reaching the number of plots we are interested in:
            if i > max_plots - 1:
                break

            # Get the anomaly and the normal values from the current signal:
            current_signal_evaluation = self.df_list[tag].loc[self.ts_label_evaluation, tag]
            current_signal_training = self.df_list[tag].loc[self.ts_normal_training, tag]

            # Plot both time series with a line plot
            ax1 = plt.subplot(gs[i])
            ax1.plot(current_signal_training, linewidth=0.5, alpha=0.8, color=colors[1])
            ax1.plot(current_signal_evaluation, linewidth=0.5, alpha=0.8, color=colors[5])

            # Title will be the tag name followed by the score:
            title = tag
            title += f' (score: {current_rank:.01f})'
                
            plt.title(title, fontsize=10)

            i += 1
            
    def get_ranked_list(self, max_signals=12):
        """
        Returns the list of signals with computed rank.
        
        PARAMS
        ======
            max_signals: integer (default: 12)
                Number of signals to consider
        
        RETURNS
        =======
            significant_signals_df: pandas.DataFrame
                A dataframe with each signal and the associated rank value
        """
        significant_signals_df = pd.DataFrame(list(self.rank.items())[:max_signals])
        significant_signals_df.columns = ['Tag', 'Rank']
        
        return significant_signals_df
    
class LookoutEquipmentScheduler:
    """
    A class to represent a Lookout for Equipment inference scheduler object.
    
    ATTRIBUTES
    ==========
        scheduler_name: string
            Name of the scheduler associated to this object
            
        model_name: string
            Name of the model used to run the inference when the scheduler
            wakes up
            
        execution_summaries: list of dict
            A list of all inference execution results. Each execution is stored
            as a dictionary.

    METHODS
    =======
        set_parameters():
            Sets all the parameters necessary to manage this scheduler object
        
        create():
            Creates a new scheduler
            
        start():
            Start an existing scheduler
            
        stop():
            Stop an existing scheduler
            
        delete():
            Detele a stopped scheduler
            
        get_status():
            Returns the status of the scheduler
            
        list_inference_executions():
            Returns all the results from the inference executed by the scheduler
            
        get_predictions():
            Return the predictions generated by the executed inference
    """
    def __init__(self, scheduler_name, model_name, region_name=DEFAULT_REGION):
        """
        Constructs all the necessary attributes for a scheduler object.
        
        PARAMS
        ======
            scheduler_name: string
                The name of the scheduler to be created or managed
                
            model_name: string
                The name of the model to schedule inference for
                
            region_name: string
                Name of the AWS region from where the service is called.
        """
        self.scheduler_name = scheduler_name
        self.model_name = model_name
        self.lookout_client = get_client(region_name)
        
        self.input_bucket = None
        self.input_prefix = None
        self.output_bucket = None
        self.output_prefix = None
        self.role_arn = None
        self.upload_frequency = None
        self.delay_offset = None
        self.timezone_offset = None
        self.component_delimiter = None
        self.timestamp_format = None
        self.execution_summaries = None
        
    def set_parameters(self,
                       input_bucket,
                       input_prefix,
                       output_bucket,
                       output_prefix,
                       role_arn,
                       upload_frequency='PT5M',
                       delay_offset=None,
                       timezone_offset='+00:00',
                       component_delimiter='_',
                       timestamp_format='yyyyMMddHHmmss'
                      ):
        self.input_bucket = input_bucket
        self.input_prefix = input_prefix
        self.output_bucket = output_bucket
        self.output_prefix = output_prefix
        self.role_arn = role_arn
        self.upload_frequency = upload_frequency
        self.delay_offset = delay_offset
        self.timezone_offset = timezone_offset
        self.component_delimiter = component_delimiter
        self.timestamp_format = timestamp_format

    def create(self):
        client_token = uuid.uuid4().hex

        create_inference_scheduler_request = {
            'ModelName': self.model_name,
            'InferenceSchedulerName': self.scheduler_name,
            'DataUploadFrequency': self.upload_frequency,
            'RoleArn': self.role_arn,
            'ClientToken': client_token,
        }

        if self.delay_offset is not None:
            create_inference_scheduler_request['DataDelayOffsetInMinutes'] = self.delay_offset

        # Setup data input configuration
        inference_input_config = dict()
        inference_input_config['S3InputConfiguration'] = dict([
            ('Bucket', self.input_bucket),
            ('Prefix', self.input_prefix)
        ])
        if self.timezone_offset is not None:
            inference_input_config['InputTimeZoneOffset'] = self.timezone_offset
        if self.component_delimiter is not None or self.timestamp_format is not None:
            inference_input_name_configuration = dict()
            if self.component_delimiter is not None:
                inference_input_name_configuration['ComponentTimestampDelimiter'] = self.component_delimiter
            if self.timestamp_format is not None:
                inference_input_name_configuration['TimestampFormat'] = self.timestamp_format
            inference_input_config['InferenceInputNameConfiguration'] = inference_input_name_configuration   
        create_inference_scheduler_request['DataInputConfiguration'] = inference_input_config

        #  Set up output configuration
        inference_output_configuration = dict()
        inference_output_configuration['S3OutputConfiguration'] = dict([
            ('Bucket', self.output_bucket),
            ('Prefix', self.output_prefix)
        ])
        create_inference_scheduler_request['DataOutputConfiguration'] = inference_output_configuration
        create_scheduler_response = self.lookout_client.create_inference_scheduler(**create_inference_scheduler_request)
        
        scheduler_status = create_scheduler_response['Status']
        print("===== Polling Inference Scheduler Status =====\n")
        print("Scheduler Status: " + scheduler_status)
        while scheduler_status == 'PENDING':
            time.sleep(5)
            describe_scheduler_response = self.lookout_client.describe_inference_scheduler(
                InferenceSchedulerName=self.scheduler_name
            )
            scheduler_status = describe_scheduler_response['Status']
            print("Scheduler Status: " + scheduler_status)
        print("\n===== End of Polling Inference Scheduler Status =====")

        return describe_scheduler_response
    
    def start(self):
        start_scheduler_response = self.lookout_client.start_inference_scheduler(
            InferenceSchedulerName=self.scheduler_name
        )

        # Wait until started:
        scheduler_status = start_scheduler_response['Status']
        print("===== Polling Inference Scheduler Status =====\n")
        print("Scheduler Status: " + scheduler_status)
        while scheduler_status == 'PENDING':
            time.sleep(5)
            describe_scheduler_response = self.lookout_client.describe_inference_scheduler(
                InferenceSchedulerName=self.scheduler_name
            )
            scheduler_status = describe_scheduler_response['Status']
            print("Scheduler Status: " + scheduler_status)
        print("\n===== End of Polling Inference Scheduler Status =====")
        
    def stop(self):
        stop_scheduler_response = self.lookout_client.stop_inference_scheduler(
            InferenceSchedulerName=self.scheduler_name
        )

        # Wait until stopped
        scheduler_status = stop_scheduler_response['Status']
        print("===== Polling Inference Scheduler Status =====\n")
        print("Scheduler Status: " + scheduler_status)
        while scheduler_status == 'STOPPING':
            time.sleep(5)
            describe_scheduler_response = self.lookout_client.describe_inference_scheduler(
                InferenceSchedulerName=self.scheduler_name
            )
            scheduler_status = describe_scheduler_response['Status']
            print("Scheduler Status: " + scheduler_status)
        print("\n===== End of Polling Inference Scheduler Status =====")
        
    def delete(self):
        if self.get_status() == 'STOPPED':
            delete_scheduler_response = self.lookout_client.delete_inference_scheduler(
                InferenceSchedulerName=self.scheduler_name
            )
            
        else:
            raise Exception('Scheduler must be stopped to be deleted.')
        
        return delete_scheduler_response
    
    def get_status(self):
        describe_scheduler_response = self.lookout_client.describe_inference_scheduler(
            InferenceSchedulerName=self.scheduler_name
        )
        status = describe_scheduler_response['Status']
        
        return status
    
    def list_inference_executions(self, execution_status=None, start_time=None, end_time=None, max_results=50):
        list_executions_request = {"MaxResults": max_results}

        list_executions_request["InferenceSchedulerName"] = self.scheduler_name

        if execution_status is not None:
            list_executions_request["Status"] = execution_status
        if start_time is not None:
            list_executions_request['DataStartTimeAfter'] = start_time
        if end_time is not None:
            list_executions_request['DataEndTimeBefore'] = end_time

        has_more_records = True
        list_executions = []
        while has_more_records:
            list_executions_response = self.lookout_client.list_inference_executions(**list_executions_request)
            if "NextToken" in list_executions_response:
                list_executions_request["NextToken"] = list_executions_response["NextToken"]
            else:
                has_more_records = False

            list_executions = list_executions + list_executions_response["InferenceExecutionSummaries"]

        self.execution_summaries = list_executions
        return list_executions
    
    def get_predictions(self):
        if self.execution_summaries is None:
            _ = self.list_inference_executions()
            
        results_df = []
        for execution_summary in self.execution_summaries:
            bucket = execution_summary['CustomerResultObject']['Bucket']
            key = execution_summary['CustomerResultObject']['Key']
            fname = f's3://{bucket}/{key}'
            results_df.append(pd.read_csv(fname, header=None))

        results_df = pd.concat(results_df, axis='index')
        results_df.columns = ['Timestamp', 'Predictions']
        results_df['Timestamp'] = pd.to_datetime(results_df['Timestamp'])
        results_df = results_df.set_index('Timestamp')
        
        return results_df