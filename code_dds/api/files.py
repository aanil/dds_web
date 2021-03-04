"""Files module."""

###############################################################################
# IMPORTS ########################################################### IMPORTS #
###############################################################################

# Standard library

# Installed
import flask_restful
import flask
import sqlalchemy

# Own modules
from code_dds.common.db_code import models
from code_dds import db
from code_dds.api.api_s3_connector import ApiS3Connector
from code_dds.api.db_connector import DBConnector
from code_dds.api.dds_decorators import token_required, project_access_required

###############################################################################
# FUNCTIONS ####################################################### FUNCTIONS #
###############################################################################


class NewFile(flask_restful.Resource):
    """Inserts a file into the database"""
    method_decorators = [project_access_required, token_required]  # 2, 1

    def post(self, _, project):
        """Add new file to DB"""

        args = flask.request.args
        if not all(x in args for x in ["name", "name_in_bucket", "subpath", "size"]):
            return flask.make_response("Information missing, "
                                       "cannot add file to database.", 500)

        try:
            # Check if file already in db
            existing_file = models.File.query.filter_by(
                name=args["name"], project_id=project["id"]
            ).with_entities(models.File.id).first()

            if existing_file or existing_file is not None:
                return flask.make_response(f"File '{args['name']}' already "
                                           "exists in the database!", 500)

            # Add new file to db
            new_file = models.File(name=args["name"],
                                   name_in_bucket=args["name_in_bucket"],
                                   subpath=args["subpath"],
                                   size=args["size"],
                                   project_id=project["id"])
            db.session.add(new_file)
            db.session.commit()
        except sqlalchemy.exc.SQLAlchemyError as err:
            db.session.rollback()
            return flask.make_response(
                f"Failed to add new file '{args['name']}' to database: {err}",
                500
            )

        return flask.jsonify({"message": f"File '{args['name']}' added to db."})


class MatchFiles(flask_restful.Resource):
    """Checks for matching files in database"""
    method_decorators = [project_access_required, token_required]  # 2, 1

    def get(self, _, project):
        """Matches specified files to files in db."""

        try:
            matching_files = models.File.query.filter(
                models.File.name.in_(flask.request.json)
            ).filter_by(project_id=project["id"]).all()
        except sqlalchemy.exc.SQLAlchemyError as err:
            return flask.make_response(
                f"Failed to get matching files in db: {err}", 500
            )

        # The files checked are not in the db
        if not matching_files or matching_files is None:
            return flask.jsonify({"files": None})

        return flask.jsonify({"files": list(x.name for x in matching_files)})


class ListFiles(flask_restful.Resource):
    """Lists files within a project"""
    method_decorators = [project_access_required, token_required]

    def get(self, _, project):
        """Get a list of files within the specified folder."""

        args = flask.request.args

        # Check if to return file size
        show_size = False
        if "show_size" in args and args["show_size"] == "True":
            show_size = True

        # Check if to get from root or folder
        subpath = "."
        if "subpath" in args:
            subpath = args["subpath"]

        files_folders = list()

        # Check project not empty
        with DBConnector() as dbconn:
            num_files, error = dbconn.project_size()
            if num_files == 0:
                if error == "":
                    return flask.make_response(error, 500)

                return flask.jsonify(
                    {"num_items": num_files,
                     "message": f"The project {project['id']} is empty."}
                )

            # Get files and folders
            distinct_files, distinct_folders, error = \
                dbconn.items_in_subpath(folder=subpath)
            if error != "":
                return flask.make_response(error, 500)

            # Collect file and folder info to return to CLI
            if distinct_files:
                for x in distinct_files:
                    info = {"name": x[0] if subpath == "."
                            else x[0].split(subpath + "/")[-1],
                            "folder": False}
                    if show_size:
                        info.update(
                            {"size": self.fix_size_format(num_bytes=x[1])}
                        )
                    files_folders.append(info)
            if distinct_folders:
                for x in distinct_folders:
                    info = {"name": x[0] if subpath == "."
                            else x[0].split(subpath + "/")[-1],
                            "folder": True}
                    if show_size:
                        folder_size, error = dbconn.folder_size(
                            folder_name=x[0])
                        if folder_size is None:
                            return flask.make_response(error, 500)

                        info.update(
                            {"size": self.fix_size_format(
                                num_bytes=folder_size
                            )}
                        )
                    files_folders.append(info)

        return flask.jsonify({"files_folders": files_folders})

    @staticmethod
    def fix_size_format(num_bytes):
        """Change size to kb, mb or gb"""

        BYTES = 1
        KB = 1e3
        MB = 1e6
        GB = 1e9

        num_bytes = int(num_bytes)
        chosen_format = [None, ""]
        if num_bytes > GB:
            chosen_format = [GB, "GB"]
        elif num_bytes > MB:
            chosen_format = [MB, "MB"]
        elif num_bytes > KB:
            chosen_format = [KB, "KB"]
        else:
            chosen_format = [BYTES, "bytes"]

        altered = int(num_bytes/chosen_format[0])
        return str(altered), chosen_format[-1]


class RemoveFile(flask_restful.Resource):
    """Removes files from the database and s3 with boto3."""
    method_decorators = [project_access_required, token_required]

    def delete(self, _, project):
        """Deletes the files"""

        with DBConnector() as dbconn:
            removed_list, not_removed_dict, not_exist_list, error = \
                dbconn.delete_multiple(files=flask.request.json)

            if not any([removed_list, not_removed_dict, not_exist_list]) and \
                    error != "":
                return flask.make_response(error, 500)

        return flask.jsonify({"successful": removed_list,
                              "not_removed": not_removed_dict,
                              "not_exists": not_exist_list})


class RemoveDir(flask_restful.Resource):
    """Removes one or more full directories from the database and s3."""
    method_decorators = [project_access_required, token_required]

    def delete(self, current_user, project):
        """Deletes the folders."""

        print(flask.request.json, flush=True)

        info_dict = {"full_removal": [],
                     "full_fail": [],
                     "removed": {},
                     "not_removed": {},
                     "not_exist": []}

        # removed_dict, not_removed_dict, not_exist_list = (
        #     {}, {}, [])

        with DBConnector() as dbconn:

            for x in flask.request.json:
                print(f"\n{x}", flush=True)
                # Get all files in the folder
                distinct_files, _, error = \
                    dbconn.items_in_subpath(folder=x)

                print(distinct_files, flush=True)
                print(error, flush=True)
                # Error with db --> folder error
                if error != "":
                    info_dict["not_removed"][x] = {"dir_error": error}
                    continue

                # No files --> folder does not exist
                if not distinct_files:
                    info_dict["not_exist"].append(x)
                    continue

                # Delete files
                removed, not_removed, _, _ = \
                    dbconn.delete_multiple(
                        files=[y[0] for y in distinct_files])

                print(removed, flush=True)

                # Check if error with S3 connection
                if None in [removed, not_removed] and error != "":
                    info_dict[x]["dir_error"] = error
                    continue

                if len(removed) == len(distinct_files):
                    info_dict["full_removal"].append(x)
                elif len(not_removed) == len(distinct_files):
                    info_dict["full_fail"].append(x)
                else:
                    info_dict["removed"][x] = removed
                    info_dict["not_removed"][x] = not_removed

        return flask.jsonify(info_dict)
