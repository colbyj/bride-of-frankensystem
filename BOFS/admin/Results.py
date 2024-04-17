from sqlalchemy.orm import Query
from BOFS.globals import db, questionnaires, page_list
import sqlalchemy
from .util import escape_csv, questionnaire_name_and_tag, condition_num_to_label
from flask  import current_app
import pandas as pd


class Results(object):
    def __init__(self, filter_criterion=None):
        self.column_list = []
        self.export_data: dict[dict] | dict = {}
        self.query_participants: Query
        self.query_filter_criterion = filter_criterion

        self.handle_participants_table()
        self.handle_questionnaires()
        self.handle_custom_exports()

    def handle_participants_table(self) -> None:
        """
        Add participant columns to column_list and their data to export_data.
        :param column_list: A list of strings that will be the columns in the CSV export.
        :param export_data: Gets updated with data for the participants
        :return: A SQLAlchemy query.
        """
        self.query_participants = db.session.query(db.Participant)

        if self.query_filter_criterion is not None:
            self.query_participants = self.query_participants.filter(self.query_filter_criterion)

        self.column_list.extend([
            "participantID",
            "externalID",
            "condition",
            "duration",
            "finished"
        ])

        query_result = self.query_participants.all()

        for row in query_result:
            self.export_data[row.participantID] = {
                'participantID': row.participantID,
                'externalID': row.mTurkID,
                'condition': condition_num_to_label(row.condition),
                'duration': row.duration,
                'finished': row.finished
            }

    def handle_questionnaires(self) -> None:
        list_of_questionnaires = page_list.get_questionnaire_list(include_tags=True)

        query_questionnaires = self.query_participants
        q_columns = {}
        q_calculated_columns = {}

        # First loop constructs the query and fetches the column names
        for entry in list_of_questionnaires:
            q_columns[entry] = []
            q_calculated_columns[entry] = []
            questionnaire_name, questionnaire_tag = questionnaire_name_and_tag(entry)

            # The python class that describes the questionnaire
            questionnaire = questionnaires[questionnaire_name]

            # Add the questionnaire's table/class to the query...
            questionnaire_db_class = db.aliased(questionnaire.db_class, name=entry)
            join_condition = db.and_(questionnaire_db_class.participantID == db.Participant.participantID,
                                     questionnaire_db_class.tag == questionnaire_tag
                                     )

            query_questionnaires = query_questionnaires.outerjoin(questionnaire_db_class, join_condition). \
                add_entity(questionnaire_db_class)

            # Make a list of the columns to later construct the CSV header row
            # This could also be done with questionnaire.fields
            for column in questionnaire.fetch_fields():
                self.column_list.append(entry + "_" + column.id)
                q_columns[entry].append(column.id)

            # Similarly, make a list of calculated columns to later be part of the CSV header row.
            for column in questionnaire.get_calculated_fields():
                self.column_list.append(entry + "_" + column)
                q_calculated_columns[entry].append(column)

            # Duration always gets added
            self.column_list.append(entry + "_duration")

        query_result = query_questionnaires.all()

        # Now we get the actual data
        for row in query_result:
            for entry in list_of_questionnaires:  # Need to look through the questionnaires again
                questionnaire_data = getattr(row, entry)

                if questionnaire_data:
                    # Regular columns first
                    for col in q_columns[entry]:
                        self.export_data[row.Participant.participantID][entry + "_" + col] = (
                            getattr(questionnaire_data, col))

                    # Now calculated columns
                    for col in q_calculated_columns[entry]:
                        if questionnaire_data:
                            self.export_data[row.Participant.participantID][entry + "_" + col] = (
                                getattr(questionnaire_data, col)())

                    # Duration always gets added
                    self.export_data[row.Participant.participantID][entry + "_duration"] = questionnaire_data.duration()

    def handle_custom_exports(self) -> None:
        # Repeated measures in other tables...
        custom_exports = []

        for export in current_app.config['EXPORT']:
            levels, fields, base_query = self.create_export_base_query(export)
            custom_exports.append({'options': export, 'fields': fields, 'base_query': base_query, 'levels': levels})

        # For custom exports, add columns based on levels determined by prior query
        for export in custom_exports:
            if export['levels']:
                for level in export['levels']:
                    for field in export['options']['fields']:
                        column_header = str.format("{}", field)
                        for level_name in level:
                            column_header += str.format("_{}", str(level_name).replace(" ", "_"))
                        self.column_list.append(column_header)
            else:
                for field in export['options']['fields']:
                    self.column_list.append(str.format(u"{}", field))

        query_result = self.query_participants.all()

        # Now we get the actual data
        for row in query_result:
            participant_id = row.participantID

            for export in custom_exports:
                query = export['base_query']
                query = query.filter(db.literal_column('participantID') == row.participantID)
                custom_export_data = query.all()  # Running separate queries will get the job done, but be kind of slow with many participants...

                export_row_index = 0
                for custom_export_row in custom_export_data:
                    for field in export['fields']:
                        export_column_name = field
                        if export['levels']:
                            export_column_name = field + "_" + str(export['levels'][export_row_index][0])

                        self.export_data[participant_id][export_column_name] = getattr(custom_export_row, field)

                    export_row_index += 1

    def create_export_base_query(self, export_definition: dict) -> tuple[list, list, "Query"]:
        """
        Builds the base query for exporting values in blueprint-defined tables.
        To be used for each entry in the config's EXPORT
        :param export_definition:
        :return: levels, fields, baseQuery
        """
        table = getattr(db, export_definition['table'])

        levels = None
        fields = []
        filter = None
        groupBy = None
        orderBy = None
        having = None

        if 'filter' in export_definition and export_definition['filter'] != '':
            filter = db.text(export_definition['filter'])

        if 'order_by' in export_definition and export_definition['order_by'] != '':
            orderBy = getattr(table, export_definition['order_by'])

        # determine how many columns to add to the export. If group_by is not used, then it's just one column
        if 'group_by' in export_definition and export_definition['group_by'] != '':
            if 'having' in export_definition and export_definition['having'] != '':  # Having can only work if group_by is used.
                having = db.text(export_definition['having'])

            levelsQ = db.session.query()

            if isinstance(export_definition['group_by'], list):
                groupBy = []
                for gb in export_definition['group_by']:
                    groupBy.append(getattr(table, gb))
                    levelsQ = levelsQ.add_columns(getattr(table, gb))
                    levelsQ = levelsQ.group_by(getattr(table, gb))
            else:
                groupBy = getattr(table, export_definition['group_by'])
                levelsQ = levelsQ.add_columns(groupBy)
                levelsQ = levelsQ.group_by(groupBy)

            if orderBy:
                levelsQ = levelsQ.order_by(orderBy)

            if filter is not None:
                levels = levelsQ.filter(filter).all()
            else:
                levels = levelsQ.all()

        # pk = db.inspect(table).primary_key[0]
        baseQuery = db.session.query(table)

        if groupBy:
            if isinstance(groupBy, list):
                for gb in groupBy:
                    baseQuery = baseQuery.group_by(getattr(table, 'participantID'), gb)
            else:
                baseQuery = baseQuery.group_by(getattr(table, 'participantID'), groupBy)

            if having is not None:
                baseQuery = baseQuery.having(having)
        else:
            baseQuery = baseQuery.group_by(getattr(table, 'participantID'))

        if orderBy:
            baseQuery = baseQuery.order_by(orderBy)

        if filter is not None:
            baseQuery = baseQuery.filter(filter)

        # Add the fields to the basequery
        for field in export_definition['fields']:
            if hasattr(table, field) and callable(getattr(table, field)):
                continue  # We can't include this python property as part of the query
            fields.append(field)
            baseQuery = baseQuery.add_columns(db.literal_column(export_definition['fields'][field]).label(field))

        return levels, fields, baseQuery

    def build_data_frame(self) -> "pd.DataFrame":
        data = []
        for key in self.export_data:
            data.append(self.export_data[key])

        return pd.DataFrame(data)

    def build_export_csv(self) -> str:
        csv_string = ",".join(self.column_list) + "\n"  # CSV Header

        for row in self.export_data.values():
            csv_line = ""
            for column in self.column_list:
                if column in row:
                    csv_line += escape_csv(row[column]) + ","
                else:
                    csv_line += ","

            csv_string += csv_line[:-1] + "\n"

        return csv_string[:-1]  # return everything except last line break

