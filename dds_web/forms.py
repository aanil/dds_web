"""Forms used in DDS web"""

# IMPORTS ################################################################################ IMPORTS #

# Standard library

# Installed
import flask_wtf
import wtforms

# Own modules

# FORMS #################################################################################### FORMS #


class RegistrationForm(flask_wtf.FlaskForm):
    """User registration form."""

    first_name = wtforms.StringField("first name", validators=[wtforms.validators.InputRequired()])
    last_name = wtforms.StringField("last name", validators=[wtforms.validators.InputRequired()])
    facility_name = wtforms.StringField("facility name")
    email = wtforms.StringField(
        "email", validators=[wtforms.validators.Email()], render_kw={"readonly": True}
    )
    username = wtforms.StringField(
        "username",
        validators=[wtforms.validators.InputRequired(), wtforms.validators.Length(min=8, max=20)],
    )

    # At least: (one lower case letter)(one upper case letter)(one digit)(special character)
    password = wtforms.PasswordField(
        "password",
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Length(min=10, max=64),
            wtforms.validators.EqualTo("confirm", message="Passwords must match!"),
            wtforms.validators.Regexp(
                regex="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9])",
                message="At least one: Lower case letter, Upper case letter, Digit, Special character.",
            ),
        ],
    )
    confirm = wtforms.PasswordField("Repeat password")
    submit = wtforms.SubmitField("submit")
