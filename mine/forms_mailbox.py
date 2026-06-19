from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length
from wtforms.fields import MultipleFileField


class GraphComposeForm(FlaskForm):
    to_addresses = TextAreaField("To", validators=[DataRequired(), Length(max=4000)])
    cc_addresses = TextAreaField("CC", validators=[Length(max=4000)])
    bcc_addresses = TextAreaField("BCC", validators=[Length(max=4000)])
    subject = StringField("Subject", validators=[DataRequired(), Length(max=300)])
    body = TextAreaField("Message body", validators=[DataRequired(), Length(max=20000)])
    attachments = MultipleFileField("Attachments")
