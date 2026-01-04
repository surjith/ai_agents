from pydantic import BaseModel, Field, EmailStr

class RecordUserDetailsModel(BaseModel):
    email: EmailStr = Field(..., description="The user's email address.")
    name: str = Field("Name not provided", description="The user's name.")
    notes: str = Field("No notes", description="Additional notes provided by the user.")

class RecordDataImprovementModel(BaseModel):
    question: str = Field(..., description="The data request question that couldn't be answered by the agent.")
    category: str = Field("General", description="The category of the data request.")
